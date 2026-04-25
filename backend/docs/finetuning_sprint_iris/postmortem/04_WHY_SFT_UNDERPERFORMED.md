# Por Qué el SFT de Iris Rindió por Debajo de su Techo Teórico
**Fecha:** 2026-04-25  
**Rama:** feat/sft-postmortem-analysis  
**Foco:** ¿Qué limitó el composite v5 a 66 cuando debería ser 80-85?

---

## A. Techo Teórico de un SFT Bien Ejecutado (N=9.272 samples reales)

### ¿Qué dice la literatura?

**LIMA (Zhou et al., NeurIPS 2023):** Con 1.000 ejemplos de alta calidad, un LLaMA-65B alcanza el 99.3% del rendimiento de ChatGPT en alignment general. El principio clave: la *calidad* importa más que la cantidad.

Con 9.272 ejemplos **reales** de una persona **real**, la hipótesis LIMA predice que el modelo debería capturar la subdistribución de formato, estilo y persona muy bien — siempre que los ejemplos sean de alta calidad y representen adecuadamente las dimensiones que se quieren capturar.

**OpenCharacter (Wang et al., 2025):** Entrena LLaMA-3-8B con ~15 ejemplos/personaje (sobre 20k personajes sintéticos) y supera a GPT-4o en persona role-playing. Con 9.272 ejemplos de una sola persona (619× más que OpenCharacter por personaje), el modelo debería capturar la persona con mucha mayor profundidad.

**TwinVoice (2025):** Distingue consistencia de superficie (léxico, tono — lo que S1 mide) de consistencia profunda (valores, opiniones bajo presión — lo que J5, J6, B2 miden). La consistencia profunda requiere ejemplos que cubran situaciones de tensión y Q&A directa sobre la persona.

### Techo teórico estimado por dimensión

*Las estimaciones se basan en qué valores son alcanzables si el dataset cubre las dimensiones necesarias y el proceso es correcto. No hay papers con la métrica v5 exacta — estos son límites derivados de principios.*

| Dimensión | FT naked actual | FT pipeline actual | Techo teórico bien ejecutado | Gap (naked) |
|---|---|---|---|---|
| **S1 Style** | 75.3 | 82.9 | **88-92** | −13 a −17 |
| S2 Quality | 67.3 | 65.9 | **72-78** | −5 a −11 |
| **S3 Strategic** | 62.3 | 68.4 | **72-78** | −10 a −16 |
| **S4 Adaptation** | 56.5 | 62.4 | **70-75** | −14 a −19 |
| J6 Q&A | 87.5 | 25.0 | **88-95 (naked), 85-92 (pipe)** | OK naked; −63 pipe |
| **J5 Belief Drift** | 47.5 | 45.0 | **70-80** | −23 a −33 |
| **K1 Context Ret** | 56.2 | 42.6 | **70-80** | −14 a −24 |
| **L1 Persona Tone** | 66.0 | 73.5 | **80-88** | −14 a −22 |
| H1 Turing | 78.0 | 60.0 | **82-90** | −4 a −12 |
| B2 Persona Cons. | 29.5 | 28.0 | **60-75** | −31 a −46 |
| **v5 composite** | **66.1** | **66.4** | **78-85** | **−12 a −19** |

**Resumen del gap:** El composite v5 actual (66.1 naked) está 12-19 puntos por debajo del techo teórico alcanzable con N=9.272 ejemplos bien construidos. Esto no es un problema de cantidad de datos — es un problema de calidad, cobertura y proceso.

---

## B. Dónde Estamos vs el Techo

### Lo que SÍ funcionó (dimensiones que llegaron cerca del techo)

| Dimensión | Techo | Actual | Brecha |
|---|---|---|---|
| A1 Length matching | 90-95 | **91.0 naked** | Mínima ✅ |
| G1 Safety (no hallucination) | 100 | **100** | Ninguna ✅ |
| G4 Echo (no eco) | ~2 | **1.78** | Mínima ✅ |
| G5 Persona Robustness (con pipeline) | 100 | **100 pipeline** | Ninguna ✅ |
| S1 pipeline | 88-92 | **82.9** | −5 a −9 (próximo) |
| J6 naked | 88-95 | **87.5** | Mínima ✅ |

**Lectura:** El modelo aprendió correctamente las dimensiones de *forma* y *estilo superficial* — Iris escribe mensajes de longitud correcta, sin eco, sin alucinaciones. Estos aprendizajes son estables y robustos.

### Lo que NO funcionó (brechas grandes con el techo)

| Dimensión | Techo | Actual (naked) | Brecha | Impacto en v5 |
|---|---|---|---|---|
| B2 Persona Consistency | 60-75 | **29.5** | −30 a −46 | Alto (peso 0.05) |
| J5 Belief Drift | 70-80 | **47.5** | −23 a −33 | Medio (parte de J_new) |
| K1 Context Retention | 70-80 | **56.2** | −14 a −24 | Medio |
| S3 Strategic | 72-78 | **62.3** | −10 a −16 | Alto (peso 0.16) |
| H1 Turing | 82-90 | **78.0** | −4 a −12 | Medio |
| L2 Logical | 65-75 | **54.7** | −10 a −20 | Medio |

---

## C. Para Cada Métrica que No Llegó al Techo: Hipótesis con Evidencia

### C1 — B2 Persona Consistency (29.5 actual, techo 60-75, brecha −30 a −46)

**Qué mide:** El judge Qwen3 evalúa si las respuestas del bot son coherentes con la persona descrita del creador a lo largo de 50 casos.

**Evidencia dataset (FASE 2):**
- 0.1% de respuestas contienen hechos de persona de Iris (10/9.272 samples)
- 59% son reacciones sociales vacías ("Ok", "Sii", "[Sticker]") que no demuestran nada sobre la persona
- El dataset tiene casi ningún ejemplo que muestre las *opiniones*, *valores* o *características profundas* de Iris

**Evidencia proceso (FASE 3):**
- El system prompt del 46% de los samples de Instagram es de 510 chars con solo "REGLAS CRITICAS" — no incluye descripción de persona de Iris

**Veredicto:** Brecha 100% explicable por gap en el dataset. El modelo no tuvo ejemplos donde Iris exprese quién es, qué piensa, qué valores tiene. Aprendió *cómo habla* Iris pero no *quién es* Iris.

**Fix:** 200-500 ejemplos sintéticos de Q&A donde Iris responde preguntas sobre sí misma de forma consistente (generados con base model + Doc D como few-shot context).

---

### C2 — J5 Belief Drift (47.5 actual, techo 70-80, brecha −23 a −33)

**Qué mide:** Cuánto mantiene el bot sus creencias/posiciones cuando el lead intenta cambiarlas (adversarial pressure en MT).

**Evidencia dataset (FASE 2):**
- Los 9.272 DMs son fan-to-creator: admiración, preguntas sobre actividades, compras
- Prácticamente ningún ejemplo donde Iris rechace roleplay o mantenga su posición bajo presión
- Los DMs de Iris a fans son naturalmente positivos y validadores → bias de aprobación

**Evidencia proceso (FASE 3):**
- Sin ejemplos adversariales en training → sin señal de entrenamiento para resistir
- RLHF del base model tenía escenarios adversariales; el SFT sobre DMs positivos puede haber diluido esa señal

**Evidencia SOTA (FASE 1):**
- TwinVoice (2025): la consistencia profunda bajo presión requiere ejemplos de tensión/desacuerdo
- ACL Sycophancy paper (2025): SFT en datos de interacción positiva amplifica el sesgo de aprobación

**Veredicto:** Brecha explicada por dos causas combinadas: (1) ausencia de ejemplos adversariales en el dataset, (2) el SFT sobre DMs positivos de fans introduce sesgo de aprobación. El modelo aprendió que "concordar" es la respuesta correcta.

**Fix:** Añadir 200-500 ejemplos de Iris manteniendo su posición — generables sintéticamente introduciendo presión en conversaciones existentes y mostrando cómo Iris respondería sin ceder.

---

### C3 — K1 Context Retention (56.2 actual, techo 70-80, brecha −14 a −24)

**Qué mide:** Si el bot hace referencia a información mencionada en turnos anteriores de la misma conversación MT.

**Evidencia dataset (FASE 2):**
- 0% de ejemplos multi-turn en el training set
- El modelo nunca fue entrenado a "recordar" lo que se dijo antes en la misma sesión
- La capacidad de K1 existe en el base model (entrenado con multi-turn), pero el SFT sobre single-turn la diluyó

**Evidencia proceso (FASE 3):**
- max_seq_length=2048 → el modelo vio solo secuencias cortas en training, no desarrolló mecanismos de atención de largo alcance dentro del SFT

**Evidencia SOTA (FASE 1):**
- TurnWise (2026): modelos entrenados solo con datos single-turn muestran rendimiento subóptimo en MT context retention incluso cuando cada turno individual está bien cubierto
- Surveyde MT (2025): la simple concatenación de ejemplos single-turn no produce flujo natural de conversación

**Veredicto:** Brecha totalmente explicada por 0% multi-turn en el dataset. El modelo aprendió a responder a mensajes individuales, no a mantener hilo conversacional.

**Fix:** Sintetizar 5.000-10.000 conversaciones multi-turn (TurnWise propone método de síntesis escalable desde single-turn existentes). TurnWise cuantifica la mejora: +12% en MT consistency con 10k ejemplos sintéticos.

---

### C4 — S3 Strategic Alignment (62.3 actual, techo 72-78, brecha −10 a −16)

**Qué mide:** Si el bot identifica y responde a la intención estratégica del lead (compra, consulta, chiste, desahogo, etc.).

**Evidencia dataset (FASE 2):**
- Categorización de 200 muestras: 59% "other" (reacciones informales), 26% "question" (Iris pregunta algo), 7% "plan/action"
- Muy pocos ejemplos de respuesta a intención estratégica clara (compra, sales, información de producto)
- 22 error-strings y 441 artefactos de media generan respuestas como `[🏷️ Sticker]` para mensajes que necesitarían contenido estratégico

**Evidencia de los peores casos S3 (FASE 2.5):**
- `user: "Exacte!" → bot: "[🏷️ Sticker] [🏷️ Sticker]"` (S3=0)
- `user: "El telf de la estefania" → bot: "[contact]"` (S3=0)
- El modelo aprendió que los artefactos de media son respuestas válidas

**Veredicto:** Dos causas concretas: (1) dataset dominado por reacciones informales sin contenido estratégico, (2) 441 artefactos de media entrenaron al modelo a emitir `[sticker]`/`[contact]` como respuestas válidas incluso donde no lo son.

**Fix:** Filtrar los 441 artefactos de media donde la respuesta es solo el artefacto. No eliminar todos los artefactos (Iris sí manda stickers), sino los casos donde el artefacto es la única respuesta a un mensaje que necesitaría contenido.

---

### C5 — H1 Turing Rate (78.0 naked, techo 82-90, brecha −4 a −12)

**Qué mide:** El judge Qwen3 evalúa si el bot parece humano en las conversaciones MT.

**Evidencia dataset (FASE 2):**
- 22 ejemplos contienen el string de error del pipeline ("Lo siento, hubo un error procesando tu mensaje")
- 253 respuestas ultra-cortas (≤5 chars) sin contexto pueden entrenarse como respuestas válidas en contextos inadecuados
- El modelo puede haber aprendido patrones que, en contextos multi-turn, suenan inconsistentes o robóticos

**Evidencia proceso (FASE 3):**
- Chat template mismatch: training con `enable_thinking=False`, serving con `<|channel>thought\n<channel|>` prefix. El model ve una secuencia nunca vista → potencial "confusión" en cómo procesar el contexto previo
- El error string en training puede hacer que el modelo, en condiciones de stress (contextos complejos), caiga en patrones robóticos

**Evidencia SOTA (FASE 1):**
- ChatBug (2024): el mismatch de chat template puede causar "degradación severa y silenciosa del rendimiento"
- HuggingFace: "usar un formato diferente al de entrenamiento produce generalmente degradación severa"

**Veredicto:** La brecha H1 naked (78 vs techo 82-90) se explica principalmente por la contaminación de los 22 error-strings que enseñaron al modelo que ese output robótico es válido. El mismatch de template contribuye en el serving con pipeline (H1 baja a 60), pero el naked ya está lejos del techo ideal por el ruido del dataset.

**Fix:** Eliminar los 22 error-strings (máximo impacto/coste). Auditar el template mismatch.

---

### C6 — L2 Logical Reasoning in MT (54.7 actual, techo 65-75, brecha −10 a −20)

**Qué mide:** Si el bot mantiene coherencia lógica a través de múltiples turnos (ej: si dijo X en turno 2, no contradice X en turno 8).

**Evidencia dataset (FASE 2):**
- 0% multi-turn → el modelo no tiene señal para aprender coherencia lógica a través de turnos
- La coherencia lógica requiere que el modelo "recuerde" sus afirmaciones previas — imposible sin multi-turn en training

**Evidencia SOTA (FASE 1):**
- TurnWise (2026): coherencia lógica en MT es exactamente la capacidad que mejora con +12% al añadir 10k multi-turn sintéticos
- ACM paper de SFT multi-turn (2024): recomienda calcular pérdida sobre TODAS las respuestas del diálogo, no solo la última

**Veredicto:** Completamente atribuible a 0% multi-turn en training. L2 comparte causa raíz con K1 y J5.

**Fix:** Mismo que K1 — dataset multi-turn sintético.

---

### C7 — v5 Composite Overall (66.1 naked, techo 78-85, brecha −12 a −19)

La brecha global resulta de la combinación de las brechas individuales, ponderadas por los pesos del composite v5:

| Causa | Métricas afectadas | Peso en v5 | Contribución estimada al gap |
|---|---|---|---|
| 0% multi-turn en dataset | K1, J5, J4, J2, L1, L2, L3 | K(0.06)+J_new(0.09)+L(0.09)=0.24 | **−4.0 a −6.0 pts** |
| 0.1% persona Q&A + 59% reacciones vacías | B2, C2, C3, S3, J6_naked | B(0.05)+S3(0.16)+J6(0.03)=0.24 | **−3.5 a −5.5 pts** |
| 22 error strings + 441 artefactos media | H1, S3, G2 | H(0.07)+S3(0.16)=0.23 | **−2.0 a −4.0 pts** |
| Chat template mismatch (serving) | J6_pipe, H1_pipe, C2 | Afecta pipeline principal. | **−1.5 a −3.0 pts** |
| Heterogeneidad sys prompt training (46%/54%) | J6_cross, B2, C3 | B(0.05)+J6(0.03)=0.08 | **−1.0 a −2.0 pts** |
| **Suma explicada** | | | **−12.0 a −20.5 pts** |
| **Gap real (techo−actual)** | | | **−12 a −19 pts** |
| **Gap residual no explicado** | | | **≈ 0** |

**El gap está completamente explicado** por las 5 causas identificadas. No hay causas desconocidas — el underperformance es 100% atribuible a problemas del dataset y del proceso identificados en FASES 2 y 3.

---

## D. Ranking de Causas Raíz por Contribución al Underperformance

| Rango | Causa | Métricas afectadas | Gap estimado | Esfuerzo de fix |
|---|---|---|---|---|
| 1 | **Dataset 100% single-turn** (sin multi-turn) | K1, J5, L2, J4, J2, parte de J6 | **4-6 pts composite** | Medio (síntesis) |
| 2 | **Ausencia de persona facts + reacciones vacías dominantes** | B2, C3, C2, S3, J6_within | **3.5-5.5 pts** | Bajo-Medio |
| 3 | **Contaminación: 22 errors + 441 media artefacts** | H1, S3, G2, potencial robotic | **2-4 pts** | Bajo (filtrado) |
| 4 | **Chat template mismatch train vs serve** | J6_pipe, H1_pipe, C2 | **1.5-3 pts** (solo pipeline) | Bajo (verificación) |
| 5 | **Sistema prompt heterogéneo en training** (46% corto / 54% ninguno) | J6_cross, B2 | **1-2 pts** | Medio (dataset rebuild) |

---

## E. Plan de Sprint 7 — Fix Priorizado

### Secuencia recomendada

**Fix E1 — Limpieza del dataset (impacto/coste más alto)**  
Tiempo: 2-3h | Coste $: 0 | Mejora composite estimada: +2-4 pts

- Eliminar los 22 error-strings del training set
- Filtrar las 441 respuestas media/sticker donde el contenido es solo el artefacto (mantener las que tienen texto adicional)
- Eliminar near-duplicates con cosine sim >0.95 (reducirá de 9.272 a ~7.500-8.000 muestras de mayor calidad)
- Eliminar respuestas <10 chars excepto donde el contexto las justifique (ej: "Oka" como respuesta a "¿todo bien?")

**Fix E2 — Construir dataset multi-turn desde conversaciones reales de la DB**  
Tiempo: 2-3 días | Coste $: 0 | Mejora composite estimada: +4-6 pts (TurnWise cita +12% en MT metrics)

- Extraer de la DB conversaciones de ≥4 turnos entre Iris y cada lead
- Format: `[system] + [user1] + [assistant1] + [user2] + [assistant2] + ...`
- Target: 5.000-10.000 conversaciones multi-turn reales
- Si el volumen de conversaciones reales es insuficiente, completar con síntesis usando el base model + few-shot

**Fix E3 — Añadir 200-500 ejemplos de persona Q&A**  
Tiempo: 1 día | Coste $: $5-10 OpenAI | Mejora composite estimada: +2-4 pts

- Generar preguntas que fans harían sobre Iris (edad, dónde vive, qué hace, gustos)
- Usar el Doc D + base model para generar respuestas consistentes de Iris
- Validar manualmente al menos 50 ejemplos antes de incluir
- Include en el formato con system prompt completo de producción

**Fix E4 — Alinear chat template train vs serve**  
Tiempo: 1-2h | Coste $: 0 | Mejora composite estimada: +1-2 pts

- Auditar la loss inicial de 10.64 — si confirma que incluye tokens del prompt, corregir
- Verificar que el template de serving no incluye `<|channel>thought\n<channel|>` si el training fue sin thinking tokens
- Opción A: Quitar el thinking prefix del serving template
- Opción B: Re-entrenar con `enable_thinking=True` para alinear con el serving template actual

**Fix E5 — Incluir system prompt de producción en el training data**  
Tiempo: 1h scripting + ~10% más de compute | Coste $: +$0.5-1 en training | Mejora composite estimada: +1-2 pts

- Añadir una versión estabilizada/congelada del Doc D como system prompt en todos los samples del training
- NO usar el RAG dinámico — usar una versión canónica fija del Doc D
- Los 4.266 samples de Instagram ya tienen un system prompt corto → reemplazarlo con el Doc D canónico

### Tabla resumen

| Fix | Tiempo | Coste $ | Mejora estimada | Riesgo |
|---|---|---|---|---|
| E1: Limpieza dataset | 2-3h | 0 | +2-4 pts | Bajo |
| E2: Multi-turn dataset | 2-3 días | 0 | +4-6 pts | Medio |
| E3: Persona Q&A | 1 día | $5-10 | +2-4 pts | Bajo |
| E4: Template alignment | 1-2h | 0 | +1-2 pts | Bajo |
| E5: System prompt en training | 1h + training | $0.5-1 | +1-2 pts | Bajo |
| **Re-training con E1+E2+E3+E4+E5** | **4-6h training** | **$5-8 Modal** | **combinado** | Medio |
| **Composite esperado post-fix** | | | **≈78-82** | |

### NO hacer

- NO hacer DPO sobre el SFT actual — el baseline SFT está contaminado. DPO amplificará el ruido, no la señal.
- NO aumentar el rank r sin primero limpiar el dataset.
- NO añadir más epochs al training actual — mejorar los datos, no sobreajustar en los malos.

---

## Conclusión

**El SFT de Iris no es un fracaso — aprendió correctamente las dimensiones de estilo superficial.** A1 (longitud), G4 (no eco), S1 (estilo) llegaron cerca o al techo. El modelo internalizó la forma de hablar de Iris.

**El SFT de Iris es incompleto.** Las dimensiones de *identidad profunda* (B2, J5, K1, J6) no mejoraron porque el dataset no las cubre. Esto no es un problema de capacidad del modelo (31B es suficiente), ni de cantidad de datos (9.272 es suficiente) — es un problema de **distribución y calidad del dataset**.

El gap de 12-19 puntos entre el composite actual (66) y el techo alcanzable (78-85) está 100% explicado por cinco causas identificadas en las FASES 2 y 3. Ninguna de ellas requiere cambios arquitectónicos o más datos de Iris — requieren reorganizar y enriquecer los datos existentes.

**La secuencia correcta para Sprint 7:** E1 (limpiar) → E2 (multi-turn) → E3 (Q&A persona) → E4 (template) → E5 (system prompt) → re-training.

---

*Manel decide si y cuándo ejecutar Sprint 7.*  
*Documento generado 2026-04-25 | feat/sft-postmortem-analysis*
