# W2 — Metadata Flow Audit
**Fecha:** 2026-04-16  
**Scope:** `metadata[...]` y `cognitive_metadata[...]` en `services/`, `core/`, `api/`  
**Resultado:** 114 fields únicos · 49 con consumer · **65 ORPHANS**

---

## Contexto arquitectónico

Clonnect usa dos dicts de metadata paralelos:

| Dict | Scope | Persistencia |
|------|-------|-------------|
| `cognitive_metadata` | In-memory por request, vive en `DmContext` | Solo se persiste si se copia explícitamente a `_dm_metadata` o `msg_metadata` |
| `metadata` / `msg_metadata` | DB column `messages.msg_metadata` (JSONB) | Persiste en PostgreSQL |

**Flujo:** `cognitive_metadata` → postprocessing.py construye `_dm_metadata` → `DMResponse.metadata` → `dispatch.py` copia selectivamente a `msg_metadata` → DB

Solo **3 fields de `cognitive_metadata`** acaban en DB: `best_of_n`, `type`, `best_of_n` (dispatch.py:158). El resto muere al final del request.

---

## Tabla consolidada

Ordenada: ORPHANS primero, luego DECISION, luego REFERENCE/PERSISTENCE.

### ORPHANS (65 fields — se escriben, nunca se leen)

| Field | Productor | Sistema | Veredicto |
|-------|-----------|---------|-----------|
| `audio_enriched` | `context.py:809` | Audio context | ORPHAN — flag booleano no consumido |
| `blacklist_replacement` | `postprocessing.py:240` | Postprocess | ORPHAN — flag de sustitución de blacklist |
| `cache_prefix_hash` | `context.py:1081` | Cache boundary | ORPHAN — hash calculado, no leído |
| `commitments_pending` | `context.py:435` | Context/memory | ORPHAN — compromisos detectados, no usados |
| `context_sections` | `context.py:1060` | Cache boundary | ORPHAN — lista de secciones del prompt |
| `dna_full_analysis_triggered` | `context.py:520` | DNA/profile | ORPHAN — flag de análisis, acción ya ejecutada |
| `dna_seed_created` | `context.py:490` | DNA/profile | ORPHAN — flag post-acción |
| `dna_update_scheduled` | `post_response.py:212` | DNA/profile | ORPHAN — flag post-scheduling |
| `echo_detected` | `postprocessing.py:?` | Echo detection | ORPHAN |
| `echo_detected_no_pool` | `postprocessing.py:?` | Echo detection | ORPHAN |
| `email_asked` | `post_response.py:367` | Email capture | ORPHAN — acción ya registrada en `record_email_ask()` |
| `email_captured` | `post_response.py:340` | Email capture | ORPHAN — email ya guardado en DB antes de escribir el field |
| `expire_reason` | `?` | Media | ORPHAN |
| `failover_from` | `?` | LLM failover | ORPHAN — proveedor origen del failover |
| `failover_to` | `?` | LLM failover | ORPHAN — proveedor destino del failover |
| `gold_examples_injected` | `context.py:?` | Few-shot | ORPHAN — flag de inyección |
| `guardrail_triggered` | `postprocessing.py:365` | Safety | ORPHAN — guardrail activado, razón no persistida |
| `hier_memory_chars` | `context.py:?` | Hier. memory | ORPHAN — estadística de chars inyectados |
| `hier_memory_injected` | `context.py:?` | Hier. memory | ORPHAN — flag de inyección |
| `hier_memory_levels` | `context.py:?` | Hier. memory | ORPHAN — num niveles en memoria jerárquica |
| `history_compaction` | `generation.py:430` | Compaction | ORPHAN — flag de compactación ejecutada |
| `history_compaction_kept` | `generation.py:431` | Compaction | ORPHAN — nº mensajes mantenidos |
| `history_compaction_pool` | `generation.py:432` | Compaction | ORPHAN — nº mensajes en pool |
| `intent_override` | `detection.py:116` | Detection | ORPHAN — override a `media_share`, no re-leído |
| `is_empty_message` | `detection.py:?` | Detection | ORPHAN |
| `is_short_affirmation` | `detection.py:?` | Detection | ORPHAN — detección de afirmaciones cortas |
| `lead_warmth` | `context.py:975` | Relational | ORPHAN — warmth score calculado, no consumido |
| `length_hint_injected` | `context.py:?` | Length hint | ORPHAN — flag de inyección del hint |
| `loop_detected` | `postprocessing.py:?` | Loop detection | ORPHAN |
| `loop_truncated` | `postprocessing.py:?` | Loop detection | ORPHAN |
| `max_tokens_category` | `generation.py:?` | Generation | ORPHAN — categoría de max_tokens seleccionada |
| `payment_link_injected` | `postprocessing.py:?` | Payment | ORPHAN — flag de inyección de link de pago |
| `ppa_refined` | `postprocessing.py:330` | PPA | ORPHAN — flag de refinamiento PPA |
| `ppa_score` | `postprocessing.py:326` | PPA | ORPHAN — score de alineación PPA |
| `ppa_scores` | `postprocessing.py:327` | PPA | ORPHAN — scores detallados PPA |
| `preference_profile` | `context.py:?` | Preferences | ORPHAN — perfil de preferencias del lead |
| `prompt_injection_attempt` | `detection.py:103` | Security | ORPHAN — intento de inyección detectado, NO alertado |
| `prompt_truncated` | `context.py:?` | Context | ORPHAN — flag de truncado del prompt |
| `query_expanded` | `context.py:?` | RAG | ORPHAN — flag de query expansion |
| `question_hint` | `context.py:?` | Question | ORPHAN — hint textual no consumido |
| `question_hint_injected` | `context.py:?` | Question | ORPHAN — flag de inyección |
| `rag_confidence` | `context.py:605/609/614` | RAG | ORPHAN — nivel de confianza RAG (high/medium/low) |
| `rag_details` | `context.py:625` | RAG | ORPHAN — detalles de chunks recuperados |
| `rag_disabled` | `context.py:566` | RAG | ORPHAN — flag RAG desactivado |
| `rag_reranked` | `context.py:634` | RAG | ORPHAN — flag de reranking ejecutado |
| `rag_routed` | `context.py:593` | RAG | ORPHAN — señal de routing RAG |
| `rag_signal` | `context.py:570` | RAG | ORPHAN — señal de activación RAG |
| `rag_skipped` | `context.py:568` | RAG | ORPHAN — razón de skip RAG |
| `reflexion_issues` | `postprocessing.py:?` | Reflexion | ORPHAN — issues detectados por reflexión |
| `reflexion_severity` | `postprocessing.py:?` | Reflexion | ORPHAN — severidad de issues |
| `relational_adapted` | `postprocessing.py:?` | Relational | ORPHAN — flag de adaptación relacional |
| `relationship_signals` | `context.py:?` | Relational | ORPHAN — señales de relación detectadas |
| `repetition_truncated` | `postprocessing.py:?` | Quality | ORPHAN — flag de repetición truncada |
| `response_strategy` | `generation.py:201` | Strategy | ORPHAN — estrategia seleccionada (`_determine_response_strategy`) |
| `sbs_llm_calls` | `postprocessing.py:301` | SBS | ORPHAN — nº llamadas LLM en SBS |
| `sbs_path` | `postprocessing.py:300` | SBS | ORPHAN — path de selección SBS |
| `sbs_score` | `postprocessing.py:298` | SBS | ORPHAN — score de alineación SBS |
| `sbs_scores` | `postprocessing.py:299` | SBS | ORPHAN — scores detallados SBS |
| `self_consistency_replaced` | `postprocessing.py:?` | Quality | ORPHAN — flag de self-consistency |
| `sensitive_detected` | `detection.py:125` | Security | ORPHAN — contenido sensible detectado, NO alertado |
| `sentence_dedup` | `postprocessing.py:?` | Quality | ORPHAN — flag de deduplicación de frases |
| `sticker_id` | `?` | Media | ORPHAN |
| `style_anchor` | `generation.py:307` | Generation | ORPHAN — flag de style anchor aplicado |
| `style_normalized` | `postprocessing.py:384` | Postprocess | ORPHAN — flag de normalización de estilo |
| `temperature_used` | `generation.py:?` | Generation | ORPHAN — temperatura usada para la llamada LLM |

---

### CONSUMER REAL — DECISION (campos que afectan lógica de código)

| Field | Productor | Consumers clave | Descripción |
|-------|-----------|-----------------|-------------|
| `audio_clean` | `evolution_webhook.py:939` | `media.py:403`, `evolution_webhook.py:335/701` | Texto limpio del audio para procesamiento |
| `audio_intel` | `media.py:224`, `oauth/instagram.py:882` (+4) | 14 consumers — `media.py`, `message_store.py`, `copilot/actions.py` | Inteligencia de audio (transcripción enriquecida) |
| `best_of_n` | `dispatch.py:158`, `generation.py:497`, `postprocessing.py:581` | 32 consumers — `copilot/actions.py`, `msg_metadata` | Flag de best-of-N, persiste en DB via `msg_metadata` |
| `clone_score` | `postprocessing.py:421` | 18 consumers — `analysis/`, `tests/`, `scripts/` | Score de clonación del mensaje |
| `context_signals` | `detection.py:182` | `post_response.py:156`, `context.py:871` (+10) | Señales de contexto para routing downstream |
| `detected_language` | `context.py:768` | `postprocessing.py:286/287/317` (+5) | Idioma detectado — controla compresión memo |
| `dna_data` | `context.py:442` | `post_response.py:201` | Datos DNA del lead para actualización |
| `duration` | `evolution_webhook.py:452/457` | 121 consumers | Duración de media (audio/video) |
| `emoji` | `?` | 151 consumers | Emoji del mensaje |
| `episodic_chars` | `context.py:?` | 12 consumers — `cpe_ablation.py`, tests | Chars de memoria episódica inyectada |
| `episodic_recalled` | `context.py:?` | `cpe_ablation.py:?` (+1) | Flag de episodic recall |
| `filename` | `?` | 140 consumers | Nombre de archivo de media |
| `history` | `?` | 63 consumers | Historial de conversación |
| `is_media_placeholder` | `?` | 1 consumer | Flag de placeholder de media |
| `lead_stage` | (no escrito en metadata, leído directamente) | 26 consumers | Stage del lead |
| `length_hint` | `context.py:?` | `generation.py:?` | Hint de longitud para generación |
| `link` | 4 producers | 109 consumers | URL de media/link |
| `link_preview` | 2 producers | 10 consumers | Preview de link |
| `media` | 1 producer | 53 consumers | Datos de media adjunta |
| `memory_chars` | `context.py:?` | 7 consumers — `cpe_ablation.py`, tests | Chars de memoria inyectada |
| `memory_recalled` | `context.py:?` | 19 consumers | Flag/datos de recall de memoria |
| `message_type` | `?` | 7 consumers | Tipo de mensaje (texto/audio/imagen…) |
| `msg_metadata` | 1 producer | 6 consumers — `copilot/actions.py` | Wrapper de metadata de mensaje |
| `name` | 2 producers | 3062 consumers | Nombre de entidad (campo genérico) |
| `needs_thumbnail` | 1 producer | 2 consumers | Flag de necesidad de thumbnail |
| `permalink` | 2 producers | 19 consumers | Permalink de post Instagram |
| `phone_number_id` | (heredado, no escrito) | 6 consumers | ID de teléfono WhatsApp |
| `query_expanded` (no consumido — ver ORPHANS) | | | |
| `relationship_type` | `context.py:?` | 83 consumers — `post_response.py:356`, `context.py`, `copilot` | Tipo de relación (amigo/lead/…) controla lógica |
| `render_as_sticker` | 1 producer | 5 consumers | Renderizar como sticker |
| `story` | 1 producer | 39 consumers | Datos de Instagram Story |
| `story_id` | 1 producer | 2 consumers | ID de story |
| `telegram_keyboard` | (heredado) | 2 consumers | Teclado Telegram |
| `thumbnail_url` | 2 producers | 36 consumers | URL de thumbnail |
| `transcription` | 3 producers | 19 consumers | Transcripción de audio |
| `truncation_recovery` | 2 producers | 2 consumers | Datos de recovery de truncado |
| `type` | 26 producers | 2696 consumers | Tipo de mensaje (campo más consumido del repo) |
| `url` | 10 producers | 577 consumers | URL genérica |

---

### CONSUMER REFERENCE (leídos pero sin branch decision directa)

| Field | Productor | Consumer | Notas |
|-------|-----------|----------|-------|
| `_full_prompt` | `generation.py:310` | `postprocessing.py:292` | Pasado a memo_compression |
| `cache_prefix_chars` | `context.py:1069` | `generation.py:357` | Métricas de cache |
| `captured_at` | `test_operations.py:284` | `media.py:44/115/151` | Timestamp de captura media |
| `context_signals` | `detection.py:182` | `post_response.py:156` | Señales de routing |
| `context_total_chars` | `context.py:1059` | `tests/cpe_measure_production.py:674` | Solo en tests |
| `dna_data` | `context.py:442` | `post_response.py:201` | DNA data para update |
| `episodic_recalled` | `context.py:?` | 2 consumers | Flag de recall |
| `memory_chars` | `context.py:?` | 7 consumers (tests) | Stats de memoria |
| `message_type` | `?` | 7 consumers | Tipo de mensaje |
| `msg_metadata` | 1 producer | 6 consumers | Metadata de mensaje |
| `nurturing_scheduled` | `post_response.py:244` | `analytics_manager.py:34` | Evento analytics (EventType enum) |
| `permanent_url` | 6 producers | 8 consumers | URL permanente de media |
| `question_confidence` | `context.py:?` | `context.py:883` | Confianza de pregunta |
| `question_context` | `context.py:?` | `context.py:882` | Contexto de pregunta |
| `raw_keys` | 1 producer | 1 consumer | Claves raw de media |
| `relationship_category` | `context.py:?` | `postprocessing.py:477` | Categoría relacional |
| `relationship_score` | `context.py:?` | 2 consumers | Score de relación |
| `sensitive_category` | `detection.py:?` | 1 consumer | Categoría sensible |
| `truncation_recovery` | 2 producers | 2 consumers | Recovery de truncado |

---

## Resumen ejecutivo

```
Total fields únicos:        114
─────────────────────────────────
DECISION (actúan en lógica): 37   (32%)
REFERENCE (leídos, pasados):  12   (11%)
ORPHANS (nunca leídos):       65   (57%)
```

### Sistemas cuyo output son 100% orphans (candidatos a eliminación total)

| Sistema | Fields orphan | Archivo productor | Impacto si se elimina |
|---------|--------------|-------------------|-----------------------|
| **RAG telemetry** | `rag_confidence`, `rag_details`, `rag_disabled`, `rag_reranked`, `rag_routed`, `rag_signal`, `rag_skipped` (7 fields) | `context.py:566-634` | Solo eliminar writes a cognitive_metadata; el routing RAG sigue funcionando |
| **SBS (Step-by-Step)** | `sbs_score`, `sbs_scores`, `sbs_path`, `sbs_llm_calls` (4 fields) | `postprocessing.py:298-301` | Solo eliminar writes; la lógica SBS sigue ejecutándose |
| **PPA** | `ppa_score`, `ppa_scores`, `ppa_refined` (3 fields) | `postprocessing.py:326-330` | Solo eliminar writes; PPA sigue ejecutándose |
| **Compaction telemetry** | `history_compaction`, `history_compaction_kept`, `history_compaction_pool` (3 fields) | `generation.py:430-432` | Solo eliminar writes |
| **Hier. memory telemetry** | `hier_memory_chars`, `hier_memory_injected`, `hier_memory_levels` (3 fields) | `context.py:?` | Solo eliminar writes |
| **Echo detection** | `echo_detected`, `echo_detected_no_pool` (2 fields) | `postprocessing.py:?` | Solo eliminar writes |
| **Loop detection** | `loop_detected`, `loop_truncated` (2 fields) | `postprocessing.py:?` | Solo eliminar writes |
| **Quality flags** | `blacklist_replacement`, `repetition_truncated`, `sentence_dedup`, `self_consistency_replaced` (4 fields) | `postprocessing.py:?` | Solo eliminar writes |
| **Security flags** | `prompt_injection_attempt`, `sensitive_detected` (2 fields) | `detection.py:103/125` | ⚠️ RIESGO: eliminar sin añadir alerting primero |
| **Style flags** | `style_anchor`, `style_normalized` (2 fields) | `generation.py:307`, `postprocessing.py:384` | Solo eliminar writes |

### Hallazgos de seguridad

- `prompt_injection_attempt` y `sensitive_detected` se detectan pero **nunca generan alerta, log persistente, ni acción**. Son orphans de seguridad — la detección existe pero no tiene efecto.
- `guardrail_triggered` guarda la razón del guardrail pero tampoco la persiste ni alerta externamente.

### Notas sobre falsos positivos en la clasificación

Algunos fields marcados como "CONSUMER" tienen consumers casi exclusivamente en `tests/` o `analysis/scripts/`. Estos son técnicamente leídos pero no en producción:
- `context_total_chars` — solo en `tests/cpe_measure_production.py`
- `clone_score` — 3 consumers en `analysis/`, 15 en `tests/`
- `episodic_chars` — mayoritariamente en tests de ablation

### Nota sobre `cognitive_metadata` → DB

Solo `best_of_n` de todos los fields cognitivos llega a persistirse en `messages.msg_metadata` (via `dispatch.py:158`). El resto de los 65+ fields de `cognitive_metadata` mueren al final del request HTTP.
