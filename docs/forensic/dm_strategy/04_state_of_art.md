# Fase 4 — State of the Art — Papers y repos aplicables a `dm_strategy`

**Objetivo:** contextualizar el router de política conversacional de `strategy.py` dentro del state-of-the-art 2024-2026 en dialogue policy, strategy routing, style conditioning y persona fidelity. Identificar qué técnicas son aplicables al PR forensic y cuáles son diferidas por coste/infraestructura.

---

## 1. Papers seleccionados (5)

### 1.1 Conversation Routines: A Prompt Engineering Framework for Task-Oriented Dialog Systems

- **Autor:** Giorgio Robino
- **Publicación:** arXiv:2501.11613v3, enero 2025
- **Link:** https://arxiv.org/html/2501.11613v3

**Resumen:** Introduce **Conversation Routines (CR)** — un enfoque estructurado de prompt engineering para diseñar sistemas de diálogo task-oriented usando instrucciones en natural language en vez de state machines tradicionales. CR embebe lógica de negocio, flujos condicionales y secuencias procedurales directamente en el prompt.

**Contraste rule-based vs LLM-based:**
| Rule-based (clásico) | CR (LLM-based) |
|----------------------|----------------|
| Hard-coded state machines rígidas | Flujo natural-language dentro del prompt |
| Anticipación exhaustiva de interacciones | Manejo flexible de inputs no previstos |
| Complejidad crece O(states²) | Coste lineal de mantener descripción |
| UX poco natural | UX más orgánica |
| Trade-off: latencia fija baja, determinismo | Trade-off: latencia variable, no-determinismo |

**Hallazgos clave aplicables:**
- **Para workflows de complejidad moderada**, embeber lógica procedural en el prompt produce resultados efectivos.
- **Para escenarios high-stakes con predictibilidad absoluta**, rule-based sigue siendo superior en latencia y ejecución fija.
- Los LLMs **confabulan o se desvían** de las instrucciones en interacciones inesperadas; guardrails mitigan pero no eliminan.

**Aplicabilidad a `dm_strategy`:** **ALTA.** El router actual es híbrido — clasifica con reglas Python (7 `if`) pero inyecta guidance en natural language al prompt. El paper valida este híbrido. Refuerza que **wording del hint importa** (no solo qué rama se elige): "Añade CTA suave" vs "Da info concreta" tiene impacto medible. Justifica la deuda BUG-010 (guardar hint completo para auditoría A/B de wording).

---

### 1.2 Prompting and Evaluating Large Language Models for Proactive Dialogues: Clarification, Target-guided, and Non-collaboration

- **Autores:** Yang Deng, Lizi Liao, Liang Chen, Hongru Wang, Wenqiang Lei, Tat-Seng Chua
- **Publicación:** EMNLP Findings 2023 (revisado octubre 2023; seminal para trabajo 2024-2026)
- **Link:** https://arxiv.org/abs/2305.13626

**Resumen:** Examina tres dimensiones proactivas que los LLMs "pure" manejan mal: (1) **clarification** ante queries ambiguas, (2) **target-guided dialogue** con goals específicos, (3) **non-collaborative dialogues** donde hay que rechazar requests problemáticas. Propone **Proactive Chain-of-Thought prompting**: augmenta LLMs con "goal planning capability over descriptive reasoning chains".

**Hallazgos clave:**
- LLMs sin scaffolding estratégico "dan respuestas aleatorias a queries ambiguas o fallan al rechazar peticiones".
- Structured prompting con reasoning explícito mejora significativamente la selección apropiada de estrategia.
- El modelo necesita ser **entrenado a razonar sobre goals**, no solo a producir texto fluente.

**Aplicabilidad a `dm_strategy`:**
- **Validación conceptual directa** del diseño actual: las ramas P3-P7 actúan como scaffolding proactivo. Sin hint, el LLM caería en default-chat (coincide con el comportamiento observado pre-P4 RECURRENTE en Railway, commit `f561819c`: 7.67 → 8.17 = +0.50).
- **Extensión natural para P1/P2 dormidas (BUG-004):** el portado al resolver S6 implementa exactamente el patrón "non-collaborative" del paper (rechazar venta a familia). La literatura avala que hacerlo vía hint estructurado es más fiable que via fine-tuning sin scaffold.
- **Diferido:** Chain-of-Thought entre turnos añade latencia significativa → incompatible con restricción de response_time < 2s actual. No aplicar ahora.

---

### 1.3 Infusing Theory of Mind into Socially Intelligent LLM Agents (ToMAgent)

- **Autores:** EunJeong Hwang, Yuwei Yin, Giuseppe Carenini, Peter West, Vered Shwartz
- **Publicación:** arXiv:2509.22887, septiembre 2025 (revisado abril 2026)
- **Link:** https://arxiv.org/abs/2509.22887

**Resumen:** **ToMAgent** inyecta un módulo de Theory of Mind (ToM) separado que genera hypothesis sobre beliefs, desires, intentions (BDI) del interlocutor entre turnos de diálogo. Las mental states generadas influyen la política conversacional siguiente. Evaluado en Sotopia (benchmark interactive social).

**Hallazgos clave:**
- "Even simply prompting LLMs to generate mental states between dialogue turns can significantly contribute to goal achievement" — el CoT sobre estado mental del otro mejora policy.
- **Learned strategies vs hard-coded:** ToMA usa estrategias aprendidas via DPO pairing; el paper sugiere que hard-coded rules son baseline mejorable.
- Long-horizon adaptation: mantiene calidad de relación a lo largo de turnos.

**Aplicabilidad a `dm_strategy`:**
- **Parcial.** Nuestro `_rel_score` (relationship_scorer) + `dna_relationship_type` + `conversation_state` (phase_context) juegan el papel de un ToM ligero implícito. Pero NO generamos hypothesis BDI explícitos entre turnos.
- **Limitación confirmada por el paper**: hard-coded rules son inferior asymptotic a learned policies. Es decir, el techo de `dm_strategy` con reglas estáticas está por debajo de un enfoque learned. Esto justifica **no invertir más en wording de reglas** y en su lugar priorizar portado al resolver + infraestructura para futuro learning (BUG-010 full metadata → dataset para DPO/ACT).
- **Diferido:** implementar ToM explícito requiere CoT entre turnos → latencia. Además no está en el scope del PR forensic.

---

### 1.4 Action-Based Contrastive Self-Training (ACT) for Multi-turn Conversations

- **Autores:** Grupo Google Research + colabores
- **Publicación:** ICLR 2024/2025 (citada en Google Research blog "Learning to Clarify")
- **Link:** https://research.google/blog/learning-to-clarify-multi-turn-conversations-with-action-based-contrastive-self-training/

**Resumen:** Algoritmo **quasi-online preference optimization** basado en DPO, diseñado para dialogue policy learning **data-efficient** en multi-turn. Genera pares contrastivos (action+ / action−) a partir de las acciones posibles (ej: clarificar vs proceder), permite fine-tuning del LLM sobre decisiones de strategy sin requerir miles de ejemplos humanamente labeled.

**Hallazgos clave:**
- Data-efficient: funciona con ~100-1000 pares contrastivos (antes requerían 10K+).
- Outperforms standard DPO on dialogue clarification decisions.
- **Aprende policy** en vez de depender de system prompts o rules.

**Aplicabilidad a `dm_strategy`:**
- **Diferido Q2 2026.** Requiere (a) dataset de pares contrastivos por strategy, (b) ciclo de fine-tuning, (c) decisión estratégica de si Clonnect usa modelo fine-tuned vs prompting. Hoy la arquitectura es prompting-only (Gemini Flash-Lite, sin FT).
- **Dependencia con E2 y portado al resolver**: si E2 evidencia que el estilo portado mueve B2, un dataset de pares contrastivos sobre portado on/off sería el input natural para ACT.
- **Acción concreta ahora:** BUG-010 (guardar `strategy_hint_full` en metadata) crea el dataset needed para futuro ACT tuning.

---

### 1.5 Soft-Prompt Tuning with Persona Prefixes for Frozen LLMs

- **Source:** EmergentMind topic "Deeply Contextualised Persona Prompting" + survey ACM Multi-turn Dialogue 2025
- **Link:** https://www.emergentmind.com/topics/deeply-contextualised-persona-prompting
- **Survey link:** https://dl.acm.org/doi/pdf/10.1145/3771090

**Resumen:** Compara tres approaches para persona fidelity en LLMs frozen:
1. **Full fine-tuning** (caro, requiere data, mejor fidelity).
2. **Persona prefix prompting** (barato, zero-shot, fidelity media).
3. **Soft-prompt tuning con prefijos persona aprendidos** (intermedio, ~1000x menos compute que FT, fidelity comparable a FT).

**Hallazgos clave:**
- Soft-prompts aprendidos **superan** hard-coded persona prompts en response diversity, fluency, engagingness, consistency.
- Prompt-tuning con selección dinámica via retriever network permite **fusionar múltiples aspectos de persona** adaptados al context del turno.
- **"La motivación central es atingir higher fidelity a realistic behaviors"** — reconocimiento explícito de que persona via hard-coded prompts tiene techo.

**Aplicabilidad a `dm_strategy`:**
- **Refuerza decisión CEO principio §1.1** (vocab_meta mined, no hardcoded): los soft-prompts learned superan hard-coded precisamente porque capturan patrones del corpus del creator, no reglas genéricas.
- **Validación arquitectural:** el patrón actual (Doc D persona + few-shot + strategy_hint hard-coded) es mejorable vía soft-prompts por creador cuando se tenga corpus mineable. CLAUDE.md del proyecto ya advierte del riesgo contrario: "Do NOT compress, summarize, reorder identity-defining signals while model is not fine-tuned on creator data" (Sprint 2 y Sprint 5 experiments fallaron).
- **Conclusión práctica:** mientras no haya FT o soft-prompts, **no tocar** Doc D ni el hint cualitativamente; parametrizar los datos lingüísticos (apelativos, openers, help_signals) desde mined data es el máximo que se puede hacer hoy sin regresar.

---

## 2. Repos OSS (3)

### 2.1 Rasa — `github.com/RasaHQ/rasa`

- **Stars:** 21.1k
- **License:** Apache-2.0
- **Lenguaje:** Python 99.3%
- **Último commit:** enero 2025
- **Estado 2026:** **⚠️ MAINTENANCE MODE** — la versión open-source está congelada. Desarrollo activo migrado a "Rasa Pro" + CALM (Conversational AI with Language Models) — ambos comerciales.

**Relevancia para `dm_strategy`:**
- **Histórica/conceptual alta**: el patrón de Rasa (NLU → Policies → Forms → Stories) es el ancestro intelectual del router actual. `dm_strategy.py` es esencialmente una *Rule-Based Policy* trasladada a Python.
- **Práctica baja**: no aplica como dependencia — adoptarlo requeriría reescribir el pipeline completo y asumir un framework en decline. Confirma que el **futuro del sector** migra de rules a LLM-based (CALM), validando la estrategia de portar al ArbitrationLayer y progresivamente a learned policies (ToMA/ACT).

**Patterns adoptables sin dependencia:**
- **Policy ensemble priority**: Rasa ranquea políticas por confianza, no por orden estricto. Potencial mejora futura a `strategy.py`: devolver `(branch, confidence)` en vez de un string, permitiendo que generation.py decida si inyectar o no.

---

### 2.2 LangGraph — `github.com/langchain-ai/langgraph`

- **Stars:** 30.1k
- **License:** MIT
- **Lenguaje:** Python (principal), TypeScript
- **Último commit:** abril 2026 (activo)
- **Estado 2026:** ✅ ACTIVO, usado en producción por Klarna, Replit, Elastic.

**Relevancia para `dm_strategy`:**
- **Arquitectural ALTA**: modela workflows LLM como grafos de nodos + edges condicionales. `dm_strategy.py` podría modelarse como un nodo "strategy_router" con 7 edges condicionales (P1..P7) + edge default. State machine persistente con memory built-in.
- **Práctica diferida**: adoptar LangGraph requiere reescribir el DM pipeline completo. No es fit para un PR forensic surgical. Pero es candidato natural para un refactor mayor Q3/Q4 2026 si se decide modernizar la infraestructura.

**Patterns adoptables sin dependencia:**
- **Descomposición explícita** de strategy_router como función separable (puro) con signature estable → facilita migrar a LangGraph en el futuro. BUG-011 (eliminar `follower_interests` dead) y el refactor a 7 params netos en Fase 5 van en esa dirección.
- **Durable execution**: strategy.py es puro, sin side effects — fácil de orquestar si el día de mañana se quiere hacer retry sobre elecciones de strategy.

---

### 2.3 DSPy — `github.com/stanfordnlp/dspy`

- **Stars:** 16k
- **License:** MIT
- **Lenguaje:** Python
- **Estado 2026:** ✅ ACTIVO, downloads mensuales 160k.

**Relevancia para `dm_strategy`:**
- **Learned policy**: DSPy permite modelar `_determine_response_strategy` como un **Signature + Module** entrenable. La función pasaría a ser: inputs (message, intent, ...) → Signature DSPy → LM invoca con structure automática → output strategy token. Con `dspy.MIPRO` / `dspy.BootstrapFewShot` se optimizan las prompts de cada Module a partir de examples.
- **Práctica diferida Q2-Q3 2026**: adoptar DSPy requiere (a) crear dataset de examples `(input, correct_strategy)`, (b) infra de optimización, (c) decidir si queremos una LLM-call extra para seleccionar strategy (sería la 3ª llamada LLM por mensaje: IntentClassifier + StrategyRouter + Main Generator).

**Patterns adoptables sin dependencia:**
- **Typed input/output via Signature**: `strategy.py` hoy retorna `str` libre. Un enum `Strategy.{FAMILIA, AMIGO, BIENVENIDA, RECURRENTE, AYUDA, VENTA, REACTIVACION, DEFAULT}` permitiría validación estricta y preparación para futuro DSPy signature.
- **Optimizable prompt per branch**: si BUG-010 guarda hint completo en metadata, cada rama acumula training data para auto-optimizar su wording con DSPy offline jobs.

---

## 3. Resumen y aplicabilidad práctica

### 3.1 Decisión de adopción

| Técnica / Repo | Aplicar en Fase 5? | Diferir? | Razón |
|----------------|-------------------|---------|-------|
| Hybrid prompt routing (Conversation Routines) | ✅ Mantener patrón actual | — | Validado para complexity moderada |
| Proactive CoT reasoning | ❌ | Q3 2026+ | Latencia inaceptable hoy |
| ToM module explícito | ❌ | Q4 2026+ | Requiere LLM call extra; depende de FT |
| ACT / learned policy via DPO | ❌ | Q2 2026 | Dataset needed → BUG-010 lo construye |
| Soft-prompt tuning persona | ❌ | Q2 2026+ | Requiere infra FT; Railway=Gemini Flash-Lite |
| Mined vocab (apelativos, openers, help) | ✅ **vocab_meta §1.1** | — | Principio CEO aplicado; fallbacks universales |
| Policy ensemble confidence (Rasa) | ⚠️ Parcial | — | Retornar `(branch, confidence)` opcional |
| LangGraph refactor completo | ❌ | Q3/Q4 2026 | Scope mucho mayor que PR forensic |
| DSPy Signature con enum strategy | ⚠️ Parcial | — | Enum strategy = preparación, sin adoptar DSPy |

### 3.2 Alineación del PR forensic con SOA

El PR forensic (Fase 5) toma posiciones **conservadoras alineadas con el state-of-the-art**:

1. **Hybrid rule-based + LLM**: mantenido (Conversation Routines lo valida para complejidad actual).
2. **Data-derived vocab via vocab_meta**: alineado con soft-prompt tuning findings (mined > hard-coded).
3. **Gate con resolver S6 (overlap VENTA/NO_SELL)**: implementa policy ensemble de Rasa en spirit sin adoptar el framework.
4. **Full hint metadata (BUG-010)**: prepara dataset para futuro ACT/DSPy optimization.
5. **Flag ENABLE_DM_STRATEGY_HINT**: habilita A/B testing necesario para validar cambios vs SOA.
6. **Métricas Prometheus**: observabilidad necesaria para cualquier iteración learned futura.

### 3.3 Deuda arquitectural identificada (DECISIONS.md)

El forense + SOA revela que `dm_strategy` está en un **local optimum**:
- Por debajo de soft-prompt / learned policy asymptotic upper bound.
- Por encima de "no hint" (ya demostrado empíricamente por commit `f561819c`: +0.50 CCEE).
- Cambios marginales en wording de reglas probablemente producen ganancias marginales (<+1.0 CCEE).
- Saltos de doble dígito requieren migrar a learned (FT o soft-prompts) o a ToM-style agent.

**Recomendación para Plan Q2-Q4 2026:**
- **Q2 2026**: ejecutar E1 (flag on/off) + E2 (portado al resolver) según plan actual.
- **Q3 2026**: si E1+E2 no alcanzan target B2 ≥ +5, kickoff proyecto de fine-tuning por creator (requerirá Sprint dedicado).
- **Q4 2026**: considerar migración infra a LangGraph si backend crece a ≥3 creators activos con policies divergentes.

---

## 4. Sources

Papers:
- [Conversation Routines (arXiv:2501.11613v3)](https://arxiv.org/html/2501.11613v3)
- [Prompting and Evaluating Proactive Dialogues (arXiv:2305.13626)](https://arxiv.org/abs/2305.13626)
- [Infusing Theory of Mind into LLM Agents - ToMAgent (arXiv:2509.22887)](https://arxiv.org/abs/2509.22887)
- [Learning to Clarify - Action-Based Contrastive Self-Training](https://research.google/blog/learning-to-clarify-multi-turn-conversations-with-action-based-contrastive-self-training/)
- [Survey Multi-turn Dialogue (ACM 2025)](https://dl.acm.org/doi/pdf/10.1145/3771090)
- [Deeply Contextualised Persona Prompting](https://www.emergentmind.com/topics/deeply-contextualised-persona-prompting)

Repos:
- [RasaHQ/rasa](https://github.com/RasaHQ/rasa) — 21.1k ⭐, maintenance mode
- [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) — 30.1k ⭐, activo
- [stanfordnlp/dspy](https://github.com/stanfordnlp/dspy) — 16k ⭐, activo

**STOP Fase 4.** Resumen: 5 papers + 3 repos analizados; patrón actual validado para complejidad moderada; SOA learned (ToMA/ACT/soft-prompts) documentados como deuda Q2-Q4 2026. PR Fase 5 se mantiene en scope conservador alineado con SOA sin introducir dependencias nuevas.

¿Procedo con Fase 5 (implementación: vocab_meta + flag + métricas + gate overlap + fix apelativos/openers/help_signals + bootstrap migration + tests)?
