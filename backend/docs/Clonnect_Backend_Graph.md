# Clonnect Backend — Knowledge Graph Report
**Generado:** 2026-04-09 | **Herramienta:** graphify

---

## Resumen del Grafo

| Métrica | Valor |
|---------|-------|
| Nodos totales | 21,159 |
| Edges (relaciones) | 40,556 |
| Comunidades detectadas | 624 |
| Archivos analizados | 1,175 |
| Palabras procesadas | ~10M |
| Edges EXTRACTED | 66% (relaciones explícitas en código) |
| Edges INFERRED | 34% (dependencias inferidas) |

---

## God Nodes — Los 10 Nodos Más Conectados

Estos son los núcleos del sistema. Cambiarlos tiene el mayor blast radius.

| # | Nodo | Edges |
|---|------|-------|
| 1 | `BoundedTTLCache` | 364 |
| 2 | `Intent` | 325 |
| 3 | `CreatorData` | 221 |
| 4 | `IntentClassifier` | 212 |
| 5 | `DeterministicScraper` | 202 |
| 6 | `ProductInfo` | 193 |
| 7 | `CreatorProfile` | 181 |
| 8 | `UserContext` | 176 |
| 9 | `RelationshipAnalyzer` | 174 |
| 10 | Business logic services (dm_agent.py) | 170 |

---

## Conexiones Sorprendentes

Relaciones cross-archivo que probablemente no eran evidentes:

1. **Dual Profile Storage Conflict**
   `creator_profiles` y `style_profiles` sirven propósitos solapados.
   → `sys38_creator_profile_service` ↔ `sys40_style_analyzer`

2. **Dual Memory Storage Conflict**
   `MemoryStore` y `ConversationMemoryService` gestionan memoria de conversación de forma independiente.
   → Posible fuente de inconsistencias en memoria.

3. **Event Loop Blocking**
   Operaciones DB síncronas llamadas desde contexto async en fases 2-3.
   → `fase2_4_carga_generacion.md` ↔ `core/dm/phases/context.py`

4. **Clonnect Functional Inventory → DM Agent 5-Phase Pipeline**
   El inventario funcional referencia el pipeline completo del agente.

---

## 20 Comunidades Principales

| ID | Nombre | Nodos |
|----|--------|-------|
| 0 | System Audit Documentation | 711 |
| 1 | Frontend Bundle (JS) | 1,062 |
| 2 | Core DM Systems Audit | 526 |
| 3 | DM Responder Agent | 404 |
| 4 | Lead Abandonment Detection | 515 |
| 5 | Bio & Profile Extraction | 390 |
| 6 | Clone Auto-Configuration | 389 |
| 7 | Clone Setup & Onboarding | 431 |
| 8 | Copilot Response Actions | 447 |
| 9 | Bot API & Middleware | 272 |
| 10 | Vocabulary & Batch Processing | 274 |
| 11 | Bot Orchestrator | 264 |
| 12 | Best-of-N Response Selection | 232 |
| 13 | System Prompt Configuration | 270 |
| 14 | Pipeline Audit Reports | 273 |
| 15 | Data Migration Scripts | 173 |
| 16 | Style Adaptation Profiler | 195 |
| 17 | Analytics & Events | 137 |
| 18 | Personalized Ranking | 143 |
| 19 | Document Extraction | 143 |

*+ 604 subsistemas adicionales*

---

## Hiperedges Clave (Grupos de Nodos)

Relaciones grupales que no se capturan con edges individuales:

| Grupo | Tipo | Confianza |
|-------|------|-----------|
| Full DM Pipeline (Webhook → Phase 0-6 → Response) | EXTRACTED | 1.0 |
| Context Assembly Systems (Phase 2-3) | EXTRACTED | 1.0 |
| LLM Generation Provider Chain (Gemini → GPT-4o-mini fallback) | EXTRACTED | 1.0 |
| Config-Driven Provider Refactor (Steps 5-8) | EXTRACTED | 1.0 |
| Memory Subsystems (Episodic + Engine + Hierarchical) | EXTRACTED | 1.0 |
| Relationship DNA Analysis Pipeline | EXTRACTED | 1.0 |
| RAG Hybrid Search Pipeline | EXTRACTED | 1.0 |
| Feedback Learning Loop | EXTRACTED | 1.0 |
| CPE v2 Decision-Grade Metrics (L1+L2+L3) | EXTRACTED | 1.0 |
| CCEE Ablation Phases (3 Subtractive + 4 Additive + 3 Learning) | EXTRACTED | 1.0 |
| 32B LoRA Adapter Family (SFT + DPO) | INFERRED | 0.90 |
| 8B LoRA Adapter Family (SFT + DPO + MLX) | INFERRED | 0.85 |
| Dual Profile Storage Conflict ⚠️ | EXTRACTED | 1.0 |
| Dual Memory Storage Conflict ⚠️ | EXTRACTED | 1.0 |

---

## Outputs Generados

```
backend/graphify-out/
├── graph.json          — Grafo completo (21,159 nodos, 40,556 edges)
├── GRAPH_REPORT.md     — Reporte detallado completo (206KB)
└── cache/              — Cache semántica (~1035 archivos)
```

---

## Queries Sugeridas

Para explorar el grafo en futuras sesiones:

```bash
# Trace blast radius de dm_agent
/graphify query "what are the dependencies of dm_agent?"

# Entender BoundedTTLCache (god node #1)
/graphify explain "BoundedTTLCache"

# Camino entre IntentClassifier y CreatorData
/graphify path "IntentClassifier" "CreatorData"

# Explorar el conflicto de memoria
/graphify query "MemoryStore vs ConversationMemoryService"
```

---

*Reducción de tokens: 140x vs leer el corpus completo*
