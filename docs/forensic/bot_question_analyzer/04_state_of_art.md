# Bot Question Analyzer — State of the Art (papers + repos)

**Contexto:** búsqueda de literatura y frameworks 2024–2026 para turn-taking, detección de afirmaciones cortas (backchanneling), dialogue act classification y question tracking. Objetivo: validar que el enfoque regex+set del analyzer está alineado con buenas prácticas, y priorizar mejoras con soporte académico.

---

## 1. Turn-taking modeling (2024–2026)

### JAL-Turn (arXiv 2603.26515, 2025)
Framework acoustic-linguistic con cross-attention para predecir hold vs shift en sistemas spoken dialogue full-duplex. Reporta mejoras sobre baselines en benchmarks multilingual (japonés customer service + corpora públicos).

**Relevancia para Clonnect:**
- Clonnect es **text-only** (IG DMs), no spoken. La señal acústica de JAL-Turn no aplica directamente.
- Sin embargo, el **principio linguistic-only** es análogo al `BotQuestionAnalyzer`: inferir tipo de turno esperado desde texto.
- *Takeaway:* clasificar el turno del bot ≠ clasificar el turno del user. El state-of-the-art modela ambos conjuntamente. Hoy el analyzer sólo modela el turno del bot.

### MDPI Technologies Review (2025, "Turn-Taking Modelling in Conversational Systems")
Survey sistemático. Destaca:
- Backchannels ("uh-huh", "mm-hm", "yeah", "sí", "vale") son **marcadores de listening activo sin intención de tomar turno**.
- Modelarlos mal rompe la fluidez — el sistema interpreta el backchannel como respuesta sustantiva y genera réplicas excesivas.
- La importancia del **role/relationship/personality** del hablante en la velocidad de turn-taking.

**Relevancia:** este es exactamente el bug que el analyzer intenta resolver. El paper confirma que es un problema real y que requiere detección dedicada — no basta con IntentClassifier general.

### Voice Activity Projection (VAP) multilingual (NoXi corpus)
Corpus 25h, 7 idiomas (EN, FR, DE, etc.), interacciones novice-expert. Entrena modelos que predicen "next speaker" de forma multilingual. El corpus **no incluye ES/CA** — gap reconocido.

**Relevancia:** confirma que multilingual turn-taking es frontera activa; el approach `AFFIRMATION_WORDS` por idioma del analyzer es consistent con el reconocimiento de que los backchannels varían cross-lingüísticamente.

## 2. Dialogue State Tracking con LLMs (2024–2026)

### "Speech-LLM Takes It All" (arXiv 2510.09424, 2025)
Compara estrategias de context management para end-to-end DST: multimodal context, full spoken history, compressed spoken history. Resultado: **full spoken conversation as input** gana claramente.

**Relevancia:**
- Refuerza la regla de Clonnect: **no comprimir identity signals** (Doc D, few-shots).
- Para context tactical (como "question pendiente"), full history es mejor que compresión.
- El callsite `detection` del analyzer ya itera `reversed(history)` full — consistente.

### "Factors affecting in-context learning abilities of LLMs for DST" (arXiv 2506.08753, 2025)
Nearest-neighbour retrieval para seleccionar demos relevantes en ICL-based DST. Prompt templates cuidadosamente diseñados.

**Relevancia:**
- La nota inyectada ("El lead confirma interés en tus servicios.") es una forma mínima de ICL — un template estático que ancla la interpretación.
- Si sube en coverage, podría evolucionar a retrieval-based: recuperar 1-shot example de conversación pasada donde un "sí" tras pregunta similar fue resuelto correctamente.
- *Out-of-scope ahora*, pero anclaje futuro legítimo.

### "Integrating Conversational Entities and Dialogue Histories" (IWSDS 2025)
Aboga por fusión explícita de entidad + historia. En Clonnect: el analyzer ya fusiona `last_bot_message` (entidad) + afirmación del lead (evento actual).

## 3. Intent / dialogue act classification — approaches híbridos

### "Intent Classification: 2026 Techniques" (Label Your Data)
Recomienda **hybrid**: rule-based regex para casos bien definidos + ML/LLM para casos nuanced. Regex captura entities obvias (fecha, order number) sin costo de modelo pesado. DistilBERT fine-tuned para intent cuando escala.

**Relevancia directa:**
- El analyzer es puramente regex+set. Para su dominio acotado (afirmaciones cortas + 7 tipos de pregunta del bot), regex es la **elección correcta** por coste/latencia/consistencia.
- Lo que falta: **mecanismo de escape a LLM** cuando confidence < 0.7 o cuando UNKNOWN. Hoy UNKNOWN simplemente no inyecta. Alternativa: fallback llamando un micro-clasificador LLM sólo en ambiguo.

### "LLMs Aren't Enough: Build Chatbots That Truly Grasp User Intent"
Argumento: LLMs solos son caros, lentos, inconsistentes. Híbrido domina producción.

**Relevancia:** valida la arquitectura actual del analyzer (no necesita LLM para detectar "si/ok/vale"). Valida también que no conviene reemplazar por un LLM classifier.

### Rasa LLMCommandGenerator (rasa.com/blog/llm-chatbot-architecture)
Plantillas con componentes estáticos y dinámicos. Estado actual de la conversación + flows/slots definidos → LLM genera comandos.

**Relevancia:** el patrón `_Q_NOTES` del injection es **exactamente** el "static component" de Rasa — mapping determinístico de dialogue state → prompt hint. Es una implementación minimalista pero sound del mismo patrón.

## 4. Repositorios relevantes

| Repo | Estrella | Aplicabilidad |
|------|----------|---------------|
| `facebookresearch/ParlAI` | Framework training/eval diálogo. Tasks: DAC (Dialogue Act Classification) con labels "acknowledge", "agree/accept", "statement-non-opinion". | Referencia conceptual: los labels ParlAI valida que nuestras 7 categorías son un subset razonable. Switchboard-1 corpus incluye `acknowledge` como DA. |
| `bhavitvyamalik/DialogTag` | Python lib que clasifica dialogue tags usando Switchboard-1. Plug-and-play. | Útil como **baseline externo** para validar el analyzer: ¿coincide DialogTag con nuestras clases cuando le pasamos mensajes del bot? Experimento ligero. |
| `RasaHQ/rasa` | Open-source framework conversational. Intent + entity + flows. | Arquitectónicamente similar. Su `LLMCommandGenerator` es más evolucionado que `_Q_NOTES` pero el principio es idéntico. |
| `sbera7/Dialogue-act-classification` | Implementación puntual DAC. Didáctico. | Referencia académica. |

## 5. Síntesis y recomendaciones

### Lo que el analyzer hace bien (alineado con SOTA)

1. **Regex para dominio acotado** — consistente con "hybrid intent classification" (2026).
2. **Vocab multilingual ES/CA/IT/EN** — reconoce la naturaleza cross-lingüística de los backchannels.
3. **Template estático por dialogue state** (`_Q_NOTES`) — patrón equivalente al "static component" de Rasa LLMCommandGenerator.
4. **Precompilación + singleton** — producción-ready para latencia sub-ms.

### Dónde se queda corto vs. SOTA

1. **Sin fallback a LLM para ambiguos** (`UNKNOWN` o `conf < 0.7`). *Upgrade opcional*.
2. **Sin tracking longitudinal** — no recuerda preguntas bot-abiertas a través de turnos. *Out-of-scope P1*.
3. **Vocab hardcoded** — no data-derived por creador. *Addresable en Phase 5*.
4. **Sin señal explícita de backchannel vs answer** — "si" siempre es afirmación; no distingue "sí de listening" vs "sí de commit". Literatura MDPI sugiere que diferenciar mejora fluidez. *Mejora posible*.
5. **Sin evaluation corpus propio** — no hay golden set multilingual para regressions. *Addresable como Phase 5 tests*.

### Decisiones concretas para Phase 5

| Área | Decisión | Justificación |
|------|----------|---------------|
| Reemplazar regex por LLM | ❌ NO | SOTA recomienda híbrido; regex domain-acotado gana en prod. |
| Extraer vocab a JSON | ✅ SÍ | Data-derived por creador = consistency con `length_by_intent.json`. |
| Añadir emojis | ✅ SÍ | Validado por corpus propio (IG DMs tienen 👍/👌 frecuentes). |
| Fallback LLM en UNKNOWN | ⚠️ DIFERIR | Ganancia marginal vs. coste latency+tokens; esperar señal CCEE. |
| Dialogue-act labeling canónico (Switchboard) | ❌ NO (ahora) | Los 7 tipos custom son task-oriented (sales), no open-domain. Mantener. |
| Golden corpus para tests 9/10 | ✅ SÍ | Multilingual + edge cases, ver Phase 5. |

---

## Referencias

- [JAL-Turn (arXiv 2603.26515)](https://arxiv.org/abs/2603.26515)
- [Turn-Taking Modelling in Conversational Systems: A Review of Recent Advances (MDPI Technologies 2025)](https://www.mdpi.com/2227-7080/13/12/591)
- [A Survey on Recent Advances in LLM-Based Multi-turn Dialogue Systems (ACM Computing Surveys / arXiv 2402.18013)](https://dl.acm.org/doi/full/10.1145/3771090)
- [The Speech-LLM Takes It All (arXiv 2510.09424)](https://arxiv.org/abs/2510.09424)
- [Factors affecting in-context learning for DST (arXiv 2506.08753)](https://arxiv.org/html/2506.08753)
- [SIGDIAL 2025 abstracts](https://2025.sigdial.org/abstracts/)
- [Intent Classification: 2026 Techniques (Label Your Data)](https://labelyourdata.com/articles/machine-learning/intent-classification)
- [LLMs Aren't Enough: Build Chatbots That Truly Grasp User Intent (Softude)](https://www.softude.com/blog/llms-arent-enough-chatbots-that-understand-user-intent/)
- [How LLM Chatbot Architecture Works (Rasa Blog)](https://rasa.com/blog/llm-chatbot-architecture)
- [ParlAI (GitHub)](https://github.com/facebookresearch/ParlAI)
- [DialogTag (GitHub)](https://github.com/bhavitvyamalik/DialogTag)
- [NLP-progress — Dialogue](https://github.com/sebastianruder/NLP-progress/blob/master/english/dialogue.md)

---

**STOP Phase 4.** Continuar con Phase 5 (optimización).
