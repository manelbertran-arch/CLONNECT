# Sistema: Vocabulary Extractor

**Fecha auditoría:** 2026-04-02
**Módulo:** `services/vocabulary_extractor.py`
**Dependencias:** `services/relationship_analyzer.py`, `services/relationship_dna_service.py`, `services/bot_instructions_generator.py`, `services/dm_agent_context_integration.py`, `core/dm/compressed_doc_d.py`

---

## 1. Propósito

Extraer vocabulario distintivo **per-lead** de los mensajes REALES del creador usando TF-IDF. Cero hardcoding — todo es data-mined.

## 2. Arquitectura

```
build_global_corpus(creator_id)
  → DB query (paginada, LIMIT 5000)
  → tokenize() cada mensaje
  → Counter global + leads_per_word
  → Cache in-memory (TTL 1h)

get_top_distinctive_words(msgs, global_vocab, total_leads, ...)
  → extract_lead_vocabulary(msgs, min_freq=2)
  → compute_distinctiveness(TF-IDF)
  → top N palabras ordenadas por score
```

## 3. Componentes

| Función | Descripción |
|---|---|
| `STOPWORDS` | Frozenset canónico ES/CA/EN/PT/IT, compartido con compressed_doc_d y relationship_analyzer |
| `_TECHNICAL_TOKENS` | URLs, plataformas, media tokens que nunca son vocabulario |
| `_WORD_RE` | Regex word-boundary `[a-zA-Z\u00C0-\u024F]{3,}` — evita underscores/handles |
| `tokenize()` | Tokeniza texto, filtra stopwords + technical + media placeholders |
| `extract_lead_vocabulary()` | Frecuencias por lead, threshold adaptativo (min_freq=3 si >50 msgs) |
| `compute_distinctiveness()` | TF-IDF scoring: palabras usadas con muchos leads = genéricas, concentradas = distintivas |
| `get_top_distinctive_words()` | Entry point: top N palabras distintivas |
| `build_global_corpus()` | Construye corpus global desde DB con paginación y cache TTL |

## 4. Flujo de inyección en prompt

```
DNA record (vocabulary_uses)
  ↓
dm_agent_context_integration._format_dna_for_prompt() [línea 190-192]
  → "Palabras que sueles usar con esta persona: X, Y, Z"
  ↓
bot_instructions_generator.generate() 
  → NO duplica vocabulario (limpiado 2026-04-02)
```

**Punto único de inyección**: `dm_agent_context_integration.py:190-192`

## 5. Bug original y root cause

**Síntoma**: DNA contenía `['crack', 'amigo', 'preciosa', 'bro', 'compa', 'amor', 'tio']` — palabras que el creador NUNCA usó.

**Root causes**:
1. `ENABLE_DNA_AUTO_ANALYZE=false` → vocabulario nunca se extraía de datos reales
2. `clone_system_prompt_v2.py` tenía `STEFAN_METRICS` hardcodeado con vocabulario fijo
3. `VocabularyExtractor` (viejo) tenía `FORBIDDEN_WORDS` por tipo de relación
4. `bot_instructions_generator.py` duplicaba vocabulario en el prompt

## 6. Fixes aplicados

| Bug | Fix | Archivo |
|---|---|---|
| Vocabulario generado por LLM | Reescrito como data-mining TF-IDF | `vocabulary_extractor.py` |
| `STEFAN_METRICS` hardcodeado | Eliminado, `extract_creator_metrics()` usa datos reales | `clone_system_prompt_v2.py` |
| `ENABLE_DNA_AUTO_ANALYZE=false` | Cambiado a `true` | `context.py:36` |
| Duplicación vocabulario en prompt | Eliminado de `bot_instructions_generator` | `bot_instructions_generator.py` |
| Technical tokens contaminando | Añadido `_TECHNICAL_TOKENS` filter | `vocabulary_extractor.py` |
| `build_global_corpus` sin cache | Cache in-memory TTL 1h | `vocabulary_extractor.py` |
| Stopwords duplicados entre módulos | Canonical `STOPWORDS` compartido | `vocabulary_extractor.py` → importado en `compressed_doc_d.py`, `relationship_analyzer.py` |

## 7. Validación académica (FASE 6)

TF-IDF para vocabulario distintivo per-usuario validado por:
- Salemi et al. 2024 (LaMP): TF-IDF profiling para generación personalizada
- Wegmann et al. 2024: TF-IDF competitivo vs embeddings para idiosincrasias léxicas
- Tyo et al. 2024: TF-IDF + vocabulario distintivo = strong authorship attribution

**Repo referencia**: Scattertext (2.3k stars) — scaled F-score como alternativa futura.

## 8. Tests

| Test file | Tests | Cobertura |
|---|---|---|
| `tests/services/test_vocabulary_extractor.py` | 8 | Core: tokenize, stopwords, word-boundary, media, TF-IDF |
| `tests/unit/test_dm_agent_vocabulary.py` | 2 | Import + basic tokenize |
| `tests/test_vocabulary_functional.py` | 13 | 10 escenarios funcionales: Iris, Stefano, empty, per-lead, catalán, español, mixed, idempotent, old-LLM, technical tokens |

**Total: 23 tests, 0 failures.**

## 9. Limitaciones conocidas

- **Non-Latin scripts** (árabe, chino, japonés): regex `[a-zA-Z\u00C0-\u024F]` no captura. No es un problema actual — todos los creadores usan ES/CA/EN/PT/IT.
- **Cache in-memory**: se pierde en restart. Aceptable — rebuild es ~2s para creators grandes.
- **Threshold adaptativo simple**: min_freq=3 para >50 msgs. Podría ser más granular pero funciona.
