# Multi-Signal Arbitration in Conversational Agents
*Literature review — 2025–2026 | 5 papers | Date: 2026-04-22*

---

## Conclusión

**Diseño P1-P7 válido según literatura. Ajuste menor accionable: estructurar en dos capas explícitas (hard veto + arbitration) siguiendo el patrón SafeCRS.**

---

## Contexto

Clonnect tiene 4 sistemas que emiten señales sobre si vender o no (DNA Engine, Conversation State, Frustration Detector, Relationship Scorer). El diseño propuesto SalesIntentResolver resuelve su arbitraje mediante 7 prioridades ordinales (P1–P7). Esta revisión valida si el approach es correcto según literatura reciente y si hay ajustes accionables antes de implementar.

---

## Papers Revisados

| ID | Título | Venue | Hallazgo clave | Aplicabilidad |
|----|--------|-------|----------------|---------------|
| C1 | *Hierarchical Alignment: Enforcing Hierarchical Instruction-Following in LLMs* | arxiv 2604.09075 | Strict dominance ordinal valida P1-P7; sin jerarquía explícita los LLMs colapsan bajo conflicto (4.5% accuracy) | **Alta** |
| C2 | *Towards Personalized Conversational Sales Agents: Contextual User Profiling for Strategic Action* | arxiv 2504.08754 | DNA/personalidad modula el tipo de acción de venta, no solo el go/no-go; 84.9% SWR | **Alta** |
| C3 | *SafeCRS: Personalized Safety Alignment for LLM-Based Conversational Recommender Systems* | arxiv 2603.03536 | Arquitectura two-layer: hard binary veto ANTES del reasoning aprendido; 96.5% reducción de violaciones | **Alta** |
| C4 | *AgentSpec: Customizable Runtime Enforcement for Safe and Reliable LLM Agents* | arxiv 2503.18666 | Patrón Trigger→Condition→Action para reglas declarativas; 90%+ detección en 25 categorías | **Parcial** |
| C5 | *Beyond Task-Oriented and Chitchat: Proactive and Transition-Aware Conversational Agents* | EMNLP 2025 | TACT dataset para transiciones de modo; métricas Switch/Recovery; 70.1% win rate vs GPT-4o | **Baja** |

---

## Validación del Diseño P1-P7

### ¿Es correcto el approach de precedencia ordinal?

**Sí, con un matiz de implementación.**

C1 demuestra empíricamente que la precedencia ordinal estricta es superior a no tener jerarquía explícita. El mecanismo MaxSMT del paper usa pesos `w_i = B^(K-level)` con B suficientemente grande para garantizar que un L0 en conflicto con cualquier número de instrucciones L1 siempre gana — esto es exactamente el principio de P1-P7. Sin jerarquía, los LLMs resuelven por atención posicional (no determinístico), que es el problema actual de Clonnect.

El matiz: C1 y C3 convergen en que las señales más críticas deben implementarse como **hard gates binarios**, no como items en una lista que el LLM pondera. P1 (sensitive) y P2 (frustration ≥2) son hard gates; P3-P7 son el razonamiento condicional que aplica solo cuando los gates no se disparan.

### ¿El orden específico P1→P7 tiene sentido?

**Sí.** C3 valida que safety/frustration primero (P1-P2) es la arquitectura correcta para sistemas conversacionales — el paper muestra 96.5% de reducción de violaciones con este patrón. C2 valida que el DNA/relación (P3) debe modular las acciones antes de las señales de oportunidad (P6), no al revés.

### ¿Hay alternativas superiores (fusion, weighted scoring, learned routing)?

**No para el MVP.** C3 usa RL (Safe-GDPO) pero requiere datos de entrenamiento curados que Clonnect no tiene hoy. C1 usa neuro-symbolic que requiere training data y Z3. Para el volumen actual y restricciones de datos, el approach ordinal rule-based es la opción correcta.

---

## Recomendación Accionable

### Estructurar SalesIntentResolver en dos capas explícitas

En lugar de evaluar P1-P7 como una lista iterativa única, separar en dos capas en el código:

**Capa 1 — Hard Gates** (P1, P2): evaluación binaria, cortocircuito inmediato, sin pasar al LLM.
**Capa 2 — Ordinal Arbitration** (P3-P7): razonamiento condicional secuencial, aplicado solo si Capa 1 pasa.

```python
class SalesIntentResolver:

    def resolve(self, ctx: ConversationContext) -> SalesIntent:
        # CAPA 1: hard gates — cortocircuito antes de cualquier razonamiento
        if ctx.is_sensitive_action:
            return SalesIntent.NO_SELL  # P1

        if ctx.frustration_level >= 2:
            return SalesIntent.NO_SELL  # P2

        # CAPA 2: arbitraje ordinal — se ejecuta solo si los gates pasan
        return self._ordinal_arbitration(ctx)

    def _ordinal_arbitration(self, ctx: ConversationContext) -> SalesIntent:
        dna = ctx.dna_engine.relationship_type

        if dna in (DNA.FAMILIA, DNA.INTIMA):
            return SalesIntent.NO_SELL          # P3

        if ctx.scorer.suppress_products:
            return SalesIntent.REDIRECT          # P4

        if ctx.scorer.soft_suppress or dna == DNA.AMISTAD_CERCANA:
            return SalesIntent.SOFT_MENTION      # P5

        if ctx.conversation_state in (State.PROPUESTA, State.CIERRE):
            return SalesIntent.SELL_ACTIVELY     # P6

        return SalesIntent.SOFT_MENTION          # P7 default
```

**Por qué dos capas, no una lista de 7:** C3 (SafeCRS) implementa el hard veto layer antes del reasoning aprendido y obtiene 96.5% de reducción de violaciones. C1 (Hierarchical Alignment) muestra que la strict dominance de niveles superiores sobre inferiores es lo que produce el comportamiento correcto — mezclar hard gates con razonamiento ordinario en una misma función diluye la garantía.

**Beneficio práctico:** P1 y P2 nunca pasan por el LLM, lo que elimina el riesgo de que el modelo "razone alrededor" de una señal de sensitive o frustración alta. Los gates son deterministas.

---

## Follow-up Post-MVP

*(No accionable ahora — marcado para después de validar P1-P7 básico en producción)*

- **Granularidad de P6 (SELL_ACTIVELY):** C2 (CSI) muestra que "sell" no es una acción monolítica — la estrategia de persuasión debería variar por perfil de usuario (Framing, Logical Appeal, Emotional Appeal, Evidence-Based, Social Proof según DNA). Esto podría añadirse como un `persuasion_strategy` dentro de `SalesIntent.SELL_ACTIVELY` post-MVP.
- **Learned arbitration para P3-P7:** Cuando Clonnect tenga datos de conversaciones etiquetadas, el patrón Safe-GDPO de C3 permitiría aprender los umbrales de P4/P5 en lugar de definirlos manualmente.
- **Métricas Switch/Recovery:** Inspiradas en C5 (TACT), para evaluar cuántas veces el resolver transiciona correctamente (Switch rate) y recupera el tono adecuado después de un NO_SELL (Recovery rate).

---

## Referencias

| Ref | Uso |
|-----|-----|
| [2604.09075](https://arxiv.org/abs/2604.09075) | Validación principal del approach ordinal estricto |
| [2504.08754](https://arxiv.org/abs/2504.08754) | Validación de DNA como modulador de tipo de acción, no solo go/no-go |
| [2603.03536](https://arxiv.org/abs/2603.03536) | Patrón two-layer hard veto + arbitration |
| [2503.18666](https://arxiv.org/abs/2503.18666) | Patrón Trigger→Condition→Action para implementación de reglas |
| [2025.emnlp-main.672](https://aclanthology.org/2025.emnlp-main.672/) | Follow-up: métricas de transición (Switch/Recovery) |
