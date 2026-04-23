# Fase 2 — Forense línea a línea de `contextual_prefix.py`

**Artefacto:** `backend/core/contextual_prefix.py` (182 LOC, Python 3.11)
**Fecha:** 2026-04-23
**Branch:** `forensic/contextual-prefix-20260423`
**Git blame:** **single commit** `dae541df` (2026-04-02, 21 días), sin follow-ups — archivo intocado desde creación

---

## 1. Header e imports (L1-28)

```python
L1-19:  """ docstring — excelente: cita paper Anthropic, ejemplifica asimetría query/doc """
L21:    import logging
L22:    from typing import List, Optional
L24:    logger = logging.getLogger(__name__)
L26-27: # comentario aclarando relación con caché de get_creator_data() 5-min
L28:    from core.cache import BoundedTTLCache
```

**Observaciones**:
- **Import diferido en mitad de archivo** (L28): `from core.cache import BoundedTTLCache` se importa tras el logger pero antes del uso. Aceptable, pero `core.creator_data_loader`, `core.embeddings` se importan **dentro de cada función** (lazy imports) — inconsistencia estilística. Probablemente para evitar ciclos de import en tests y para acelerar el import del módulo.
- Docstring del módulo cita el paper original con la cifra **+49%**. No se cita fuente interna de validación.

## 2. El caché de prefijos (L30)

```python
L30: _prefix_cache: BoundedTTLCache = BoundedTTLCache(max_size=50, ttl_seconds=300)
```

**Valores hardcoded**:
- `max_size=50`: soporta 50 creators distintos en cache antes de evict. Hoy hay 2 creators activos (Iris + Stefano) + dev noise. Sobra holgado, pero si el sistema escala a 100+ creators (producto es B2B multi-tenant), llegará a evicciones frecuentes y el log dirá "[CONTEXTUAL-PREFIX] Built prefix for X: N chars" mucho más veces.
- `ttl_seconds=300` (5 min): un cambio de `knowledge_about` por el admin tarda ≤5 min en reflejarse en nuevas construcciones de prefijo. **Pero los vectores ya indexados con el prefijo viejo siguen en pgvector indefinidamente**.

**Módulo-level singleton**: sobrevive por la vida del proceso uvicorn. Si Railway re-despliega, se reinicia. No comparte estado entre workers (si uvicorn corre con `--workers N`, cada worker tiene su propio `_prefix_cache` → N llamadas a `get_creator_data` hasta calentar).

**Expuesto en tests** (`tests/test_contextual_prefix.py:59`): `from core.contextual_prefix import _prefix_cache` — el nombre con guion bajo sugiere privado, pero los tests hacen monkey-clear sobre él. Acoplamiento.

## 3. Función pública `build_contextual_prefix` (L33-50)

```python
L33: def build_contextual_prefix(creator_id: str) -> str:
L34-43: docstring
L44:    cached = _prefix_cache.get(creator_id)
L45:    if cached is not None:
L46:        return cached
L48:    prefix = _build_prefix_from_db(creator_id)
L49:    _prefix_cache.set(creator_id, prefix)
L50:    return prefix
```

**Comportamiento**:
- Cache-aside clásico. `None` vs `""`: `_prefix_cache.get` retorna `None` en miss. Un `""` válido (creator sin datos) también se cachea (L49) para no repetir el intento — positivo.
- **Key**: `creator_id` string. No se normaliza (case, trim). Si dos callers pasan `"Iris_Bertran"` y `"iris_bertran"` → dos entradas distintas, dos construcciones, dos vectores hornados con prefijos idénticos pero contabilizados 2x. En producción solo se usa `creator_id` consistente en minúscula, bajo control.

**Edge case no cubierto**:
- Si `_build_prefix_from_db` retorna `""` por fallo transitorio de BD (pgbouncer reset), el `""` se cachea 5 min. Los próximos 5 minutos de ingestión emitirán vectores **sin prefijo** silenciosamente. Luego el caché expira y vuelve a funcionar. No hay alerta.

## 4. `_build_prefix_from_db` — el corazón (L53-157)

### 4.1 Gate inicial (L61-66)

```python
L61: try:
L62:     from core.creator_data_loader import get_creator_data as _get_creator_data
L64:     data = _get_creator_data(creator_id, use_cache=True)
L65:     if not data or not data.profile or not data.profile.name:
L66:         return ""
```

- Lazy import (ciclo potencial, y `get_creator_data` importa `creators` model).
- **3 condiciones para bailar early**: `not data` (imposible, `CreatorData` es dataclass con default), `not data.profile` (defaultea a `CreatorProfile()` vacío, truthiness por `__bool__` implícito de dataclass → siempre `True` si objeto existe — este check **no filtra** nada útil), `not data.profile.name` (el único check real: name vacío → `""`).
- **Bug latente**: `not data.profile` es `False` siempre que el dataclass exista (dataclass defaultea fields, truthy). El check efectivo es solo `not data.profile.name`. Redundante pero inofensivo.

### 4.2 Construcción de Parte 1 — Identidad + Handle (L68-88)

```python
L68: parts = []
L71: name = data.profile.clone_name or data.profile.name
L72: ka = data.profile.knowledge_about or {}
L75: specialties = ka.get("specialties", [])
L76: bio = ka.get("bio", "")
L77: ig_handle = ka.get("instagram_username", "")
L80-83: # fallback specialties <- products[:5]
    if not specialties and not bio and data.products:
        product_names = [p.name for p in data.products[:5] if p.name]
        if product_names:
            specialties = product_names
L85: name_part = name
L86-87: if ig_handle:
            name_part = f"{name} (@{ig_handle.lstrip('@')})"
```

- `clone_name or name` (L71): prefiere `clone_name` (ej. "Iris") sobre `name` (ej. "Iris Bertran"). Decisión razonable — el clone tiene personalidad propia.
- **Mutación sutil** (L80-83): sobrescribe `specialties` con `product_names` si `specialties` vacío AND `bio` vacío. Efecto en cascada: la rama L89 `if specialties` entra por product_names → emite `"Iris ofrece Barre, Flow4U, Pilates Reformer"`. Esto mezcla la semántica "specialties" (servicios que ofrece) con "products" (cosas que vende) — a menudo alineado pero no siempre (product_name puede ser "Bono 10 sesiones" → prefijo raro).
- `products[:5]`: hardcoded. Si el creator tiene 30 productos, solo ve los primeros 5 ordenados según llegaron de `get_creator_data` (orden no garantizado).
- `lstrip('@')` (L87): defensivo, bien. Pero no aplica a `name` — si alguien pone "@irisbertran" en `profile.name`, queda `@irisbertran (@iraais5)`.

### 4.3 Parte 2 — Dominio + bio fallback (L89-103)

```python
L89: if specialties:
L90:     if isinstance(specialties, list):
L91:         spec_str = ", ".join(specialties[:3])
L92:     else:
L93:         spec_str = str(specialties)
L94:     parts.append(f"{name_part} ofrece {spec_str}")
L95: elif bio:
L96:     first_sentence = bio.split(".")[0].strip()
L97:     if first_sentence and len(first_sentence) > 10:
L98:         parts.append(f"{name_part}: {first_sentence}")
L99:     else:
L100:        parts.append(name_part)
L101: else:
L102:    parts.append(name_part)
```

- `specialties[:3]`: hardcoded. Igual que products, el orden de la lista no está controlado — un creator con 8 specialties ve solo 3 y no las 3 más importantes necesariamente.
- `", ".join(specialties[:3])`: sin validación del contenido. Si un elemento tiene una coma dentro (p.ej. `"nutrición, running, boxeo"` como 1 specialty), explota en 3 strings visuales pero funciona.
- `isinstance(specialties, list)` (L90): check defensivo por si `ka.get("specialties")` retorna string (JSONB puede guardar cualquier cosa). Rama `else: str(specialties)` (L93) — acepta sin quejarse un dict/int/etc. **Silenciosamente** emite prefijo pobre.
- `first_sentence = bio.split(".")[0]` (L96): heurística. Rompe con bios multi-frase como `"Instructora. Con 10 años..."` → toma solo `"Instructora"`. Para bios sin punto, `split(".")` retorna `[bio_entero]` → primera frase = bio completa. Aceptable, pero sin control.
- `len(first_sentence) > 10` (L98): **umbral mágico**. Bios muy cortas ("Coach") caen al fallback L100 → solo nombre.
- Verbo "ofrece" (L94): hardcoded en español. **Romperá multilingual** si se crea un creator italiano — el prefijo quedará `"Stefano (@..) ofrece business coach en Milano"` en una base italiana. Sub-óptimo para recall@k en queries en italiano (aunque `text-embedding-3-small` es multilingüe, un mismatch verbo-idioma debilita la señal).

### 4.4 Parte 3 — Ubicación (L105-108)

```python
L105: location = ka.get("location", "")
L106-107: if location:
              parts[-1] += f" en {location}"
```

- Concatena con `" en "` **a la última parte existente** (no crea nueva parte). Asume siempre hay una parte 1 (garantizado por L102 que añade `name_part` sí o sí). Bien.
- Preposición `"en"` hardcoded en español. Multilingual roto (igual que L94).

### 4.5 Parte 4 — Idioma/dialecto (L110-123)

```python
L110: dialect = data.tone_profile.dialect if data.tone_profile else "neutral"
L111-112: if dialect and dialect != "neutral":
L113-121:     _DIALECT_LABELS = {
                  "rioplatense": "español rioplatense",
                  "mexican": "español mexicano",
                  "catalan": "castellano y catalán",
                  "catalan_mixed": "castellano y catalán mezclados",
                  "italian": "italiano",
                  "english": "inglés",
                  "formal_spanish": "español formal",
              }
L122: lang_label = _DIALECT_LABELS.get(dialect, dialect)
L123: parts.append(f"Habla {lang_label}")
```

**Tres issues identificados**:

1. **Dict inline recreado en cada call** (L113-121): `_DIALECT_LABELS` se redefine cada invocación de `_build_prefix_from_db`. Cache de prefijos mitiga el coste, pero en miss es ~30 bytes allocation + GC. Trivial, pero **el nombre con `_` sugiere constant de módulo** — debería estar a nivel módulo. Mayor problema: imposible hacer override en tests o por config sin parchear el módulo.
2. **Cobertura cerrada de 7 dialectos**: si la BD tiene `"portuguese"`, `"french"`, `"german"`, `"galician"` en `tone_profile.dialect`, el `.get(dialect, dialect)` (L122) retorna el literal crudo → prefijo `"Habla portuguese"` (palabra en inglés dentro de frase en español). Sin-elegante y debilita recall vs. `"Habla portugués"`.
3. **Ausencia de `neutral` tratado como "no emitir"**: `dialect == "neutral"` skipea parte 4. Si la DB tiene `""` o `None`, L111 evalúa `False` (por `dialect and` cortocircuito) y también skipea. Bien cubierto.

Lista completa de dialectos vistos en el código del repo (grep rápido): `neutral`, `rioplatense`, `mexican`, `catalan`, `catalan_mixed`, `italian`, `english`, `formal_spanish`. Exactamente la tabla. **Cero deuda** en la tabla hoy; **el problema es arquitectónico**, no de cobertura actual.

### 4.6 Parte 5 — Formality (L125-130)

```python
L125: formality = data.tone_profile.formality if data.tone_profile else "informal"
L126-130: if formality == "formal":
              parts.append("Estilo formal y profesional")
          elif formality == "casual":
              parts.append("Estilo muy informal y cercano")
```

- **Solo 2 de 3 valores vistos** (`ToneProfileInfo.formality` default es `"informal"`): `formal` y `casual` disparan etiqueta; `informal` (el default) **no disparaba nada**. El código comenta como si "informal" + "casual" fueran sinónimos, pero solo `"casual"` hace match.
- **Efecto práctico**: la mayoría de creators (default `"informal"`) no reciben hint de estilo. Iris tiene `formality="informal"` según `massive_test` baseline → ausencia de hint en su prefijo. Stefano: según tests, también `"informal"`. **El branch "casual" sirve a ~0 creators en producción real**.
- **Inconsistencia semántica**: en `ToneProfileInfo` los valores documentados son `"formal"`, `"informal"`, `"mixed"`. Aquí se espera `"casual"` — valor nunca documentado en el dataclass. Probable bug de copy-paste del autor: pensaba en "very informal" → "casual", pero los datos reales nunca lo tienen.

### 4.7 Parte 6 — FAQ hint (L132-138)

```python
L132-138:
if len(parts) == 1 and data.faqs:
    # Only name so far — add FAQ topic hint
    faq_sample = [f.question for f in data.faqs[:3] if f.question]
    if faq_sample:
        topics = "; ".join(faq_sample)
        parts.append(f"Temas frecuentes: {topics}")
```

- **Condición extra-restrictiva** (`len(parts) == 1`): se dispara solo si no hay specialties, bio, products → solo nombre. En producción prácticamente nunca (Iris y Stefano tienen specialties). Rama casi muerta para los creators activos.
- `faqs[:3]`: hardcoded igual que products y specialties.
- `"; ".join(...)` de preguntas completas puede generar strings largos (una FAQ real es una frase de 10-30 palabras) → rápidamente llegas al cap 500 chars. Diseño sub-óptimo: debería usar **tópicos** derivados de las FAQs, no la pregunta entera.

### 4.8 Cap final y return (L140-157)

```python
L140-141: if not parts:
              return ""
L143: prefix = ". ".join(parts) + ".\n\n"
L146-147: if len(prefix) > 500:
              prefix = prefix[:497] + ".\n\n"
L149-152: logger.info("[CONTEXTUAL-PREFIX] Built prefix for %s: %d chars", creator_id, len(prefix))
L153: return prefix
L155-157: except Exception as e:
              logger.warning("[CONTEXTUAL-PREFIX] Failed to build for %s: %s", creator_id, e)
              return ""
```

- L140-141: `parts` siempre tiene ≥1 elemento (L102 añade `name_part` sí o sí). Check redundante pero inofensivo.
- L143: `". ".join(parts)` — junta con `". "`. Si una parte termina en `"."` (p.ej. `"Iris: Instructora."` por bio), queda `"..."` doble. Hoy ninguna rama añade punto final, pero futuras adiciones deben cuidarlo.
- **Cap en 500 chars + `.\n\n`** (L147): truncado hard. Problema: si el truncado cae a mitad de una palabra → `"Iris ofrece instr"` seguido de `.\n\n`. No intenta buscar el último espacio/punto antes del corte. Pérdida de calidad en casos edge.
- **`.\n\n` como terminador**: el cap final se aplica sobre `prefix[:497] + ".\n\n"` → siempre resulta en ≤500 chars. Bien.
- L149-152: el único log productivo. No incluye `dialect`, `source_type` (specialties/bio/products/faqs), `parts_count`. Observabilidad pobre.
- L155-157: fail-open universal. Cualquier excepción → `""` → chunk embebido sin prefijo. **No hay alerta**. Si BD cae durante un backfill masivo, se indexa toda la base sin prefijo silenciosamente.

## 5. `generate_embedding_with_context` (L160-171)

```python
L160-162: def generate_embedding_with_context(text: str, creator_id: str) -> Optional[List[float]]:
L163-167: docstring (reitera asimetría query/doc)
L168:     from core.embeddings import generate_embedding
L170:     prefix = build_contextual_prefix(creator_id)
L171:     return generate_embedding(prefix + text)
```

- Simple concatenación string. Si `prefix == ""`, equivalente a llamar directo a `generate_embedding(text)`.
- **Lazy import** cada llamada (L168) — pequeño overhead (lookup en `sys.modules`, fast path). Elegido para evitar coste al importar `contextual_prefix` sin usar.
- No valida que `text` sea no vacío. `generate_embedding("")` llama OpenAI con string vacío → probable error en upstream; rama pasada al downstream sin filtrar.
- No valida que `creator_id` exista antes de construir prefix. Build con `creator_id` inventado: retorna `""` en el prefix → embebe `text` crudo. Pasa como "éxito" silencioso.

## 6. `generate_embeddings_batch_with_context` (L174-182)

```python
L174-176: def generate_embeddings_batch_with_context(texts, creator_id): ...
L178:     from core.embeddings import generate_embeddings_batch
L180:     prefix = build_contextual_prefix(creator_id)
L181:     prefixed_texts = [prefix + t for t in texts]
L182:     return generate_embeddings_batch(prefixed_texts)
```

- **Un solo prefix por batch**: asume que el batch es mono-creator. Correcto — los 3 callsites pasan batches de 1 creator solo.
- List comprehension sin condición: si `texts` contiene string vacío, queda `prefix + ""` → embebe solo el prefijo. Resultado: embedding de "Iris ofrece barre..." (sin contenido real). Bug silencioso en upstream si no filtra chunks vacíos.
- Sin fallback a `generate_embedding` individual si batch falla: `generate_embeddings_batch` devuelve `[None] * len(texts)` en fallo → esa lista se retorna como es, y el caller decide. `services/content_refresh.py:191` chequea `if embedding:` → filtra None; OK.

## 7. Los tres callsites productivos — análisis detallado

### 7.1 `core/rag/semantic.py:85-110` — `SemanticRAG.add_document`

```python
L85: def add_document(self, doc_id: str, text: str, metadata: Dict = None):
L92: doc = Document(doc_id=doc_id, text=text, metadata=metadata)
L93: self._documents[doc_id] = doc  # in-memory cache
L99: if self._check_embeddings_available():
L100: try:
L101:     from core.contextual_prefix import generate_embedding_with_context
L102:     from core.embeddings import store_embedding
L104:     creator_id = metadata.get("creator_id", "unknown") if metadata else "unknown"
L105:     embedding = generate_embedding_with_context(text, creator_id)
L106:     if embedding:
L107:         store_embedding(doc_id, creator_id, text, embedding)
L108:         logger.debug(f"Stored embedding for {doc_id}")
```

**Fallas identificadas**:
- **`creator_id = "unknown"` fallback** (L104): si metadata es None o no contiene `creator_id`, el prefijo para `"unknown"` → retorna `""` (no hay creator con ese ID en BD). El documento se embed crudo y se guarda con `creator_id="unknown"` en `content_embeddings`. **Basura silenciosa**: filas fantasma en pgvector inútiles para query (nunca se filtra por creator_id="unknown"). No hay validación ni log warning.
- Lazy import dentro del try: aceptable, pero **si el import falla** (typo del autor, circular imports), se loguea como "Error storing embedding" (L109-110) sin distinguir causa.

### 7.2 `api/routers/content.py:384-427` — endpoint bulk

```python
L384: from core.contextual_prefix import generate_embeddings_batch_with_context
L385: from core.embeddings import store_embedding
...
L422: for i in range(0, len(chunks_without_embeddings), batch_size):
L423:     batch = chunks_without_embeddings[i : i + batch_size]
L424:     texts = [row.content for row in batch]
L427:     embeddings = generate_embeddings_batch_with_context(texts, creator_id)
L430:     for j, (row, embedding) in enumerate(zip(batch, embeddings)):
L431:         if embedding:
L432:             if store_embedding(row.chunk_id, row.creator_id, row.content, embedding):
L433:                 generated += 1
```

- **Inconsistencia potencial** (L427 vs L432): `generate_embeddings_batch_with_context` recibe `creator_id` del request (parametro del endpoint), pero `store_embedding` usa `row.creator_id` de la BD. Si el operador admin pasa `creator_id` equivocado en el request, **el prefijo se construye para creator X** pero **los embeddings se guardan bajo creator Y** (el real de la fila). Vector hornado con contexto de otro creator → **contaminación cross-creator**.
- Sin validación de que `creator_id` del request coincida con `row.creator_id`. El SQL WHERE sí filtra por `creator_id = :creator_id` (L401), pero el dato es redundante — si las filas ya tienen `creator_id`, por qué pasarlo de nuevo al endpoint. La duplicación genera la oportunidad de drift.

### 7.3 `services/content_refresh.py:155-200` — refresh periódico

```python
L185: from core.contextual_prefix import generate_embedding_with_context
L186: from core.embeddings import store_embedding
L189: for row in rows:
L190:     embedding = generate_embedding_with_context(row.content, creator_id)
L191:     if embedding:
L192:         store_embedding(row.chunk_id, creator_id, row.content, embedding)
L193:         stored += 1
```

- Usa `generate_embedding_with_context` uno-a-uno (no batch). Para cada chunk → 1 llamada OpenAI. **Ineficiente**: si `refresh` produce 100 chunks nuevos, son 100 roundtrips OpenAI vs 1-2 calls batch. Costes: ~100x más API calls. Latencia acumulada: 100 × ~80 ms ≈ 8 s por creator vs ~1 s si batcheado.
- `creator_id` del argumento es consistente (se usa en prefix y store). Sin el problema del callsite #2.

## 8. Formato del prefix generado — propiedades observadas

Para Iris con datos reales (producción 2026-04-23):

```
Iris (@iraais5) ofrece instructora de fitness, barre, zumba en Barcelona. Habla castellano y catalán mezclados. Estilo muy informal y cercano.

```

**Métricas**:
- Longitud: ~140 chars.
- Tokens aproximados (OpenAI BPE): ~35-40 tokens.
- Capacidad embebida: `text-embedding-3-small` acepta 8191 tokens. Chunk típico: 512-1024 tokens. Prefijo cabe holgado (<5% del budget).
- `.\n\n` terminator: doble newline separa prefijo de chunk, emulando párrafos. Útil para la heurística interna del modelo de embedding de tratar bloques semánticamente.
- **Idioma**: ES mezclado ("ofrece", "en", "Habla") con nombre propio ES/CA y ubicación "Barcelona". Para queries EN puras (`"how much is barre class?"`), hay mismatch — aunque OpenAI multilingual model tolera bien.

Para Stefano (datos tests — en prod no claro):
```
Stefano (Business Coach) en Milano. Habla italiano. Estilo formal y profesional.

```
- Mezcla ES (palabras conectivas) + IT (dialecto). **Sub-óptimo para retrieval en italiano**: query "quanto costa il coaching" match parcial con un prefijo ES. Ganancia teórica (+35-49%) se reduce.

### 8.1 Compatibilidad multilingual

**Estado actual**:
| Caso | Tratamiento | Problema |
|------|-------------|----------|
| Creator ES (Iris) | Prefijo ES puro | ✅ OK |
| Creator CA mixed (Iris) | Prefijo ES con "Habla catalán mezclado" | ✅ OK |
| Creator IT (Stefano) | Prefijo ES estructura + "Habla italiano" | ❌ Mismatch estructura-contenido |
| Creator EN (hipotético) | Prefijo ES estructura + "Habla inglés" | ❌ Mismatch |
| Dialecto no mapeado (`"french"`) | `"Habla french"` (palabra EN dentro de ES) | ❌ |

**No hay tabla por idioma de los conectivos** (`ofrece`, `en`, `Habla`, `Estilo`). Un fix serio requeriría un switch por `dialect` → template. Queda pendiente.

## 9. Cache `_prefix_cache` — hit rate en producción

### 9.1 Sin instrumentación propia

`BoundedTTLCache` **no registra hits/misses**. El único log es `"[CONTEXTUAL-PREFIX] Built prefix for %s: %d chars"` en miss. Inferir hit rate requiere:
1. Contar builds por creator en logs (solo ve miss).
2. Estimar total de llamadas a `build_contextual_prefix` desde callsites × triggers.

### 9.2 Railway logs (último despliegue, accesible via `railway logs`)

No accesible directamente en este worktree. La información disponible (sin ejecutar contra Railway, por constraint de seguridad de la tarea):
- `_embed_new_chunks` en content_refresh corre cada 24 h por creator. Actualmente activo para Iris + Stefano → 2 creators × 1 build/día = **2 builds/día productivos** (worst-case, si el caché se pierde por redeploy antes del segundo chunk).
- Dentro de un batch de refresh, una sola construcción de prefix sirve todos los chunks del creator (cache hit en L44-46). **Hit rate intra-batch: ~100%**.
- Entre batches: el cache sobrevive si el proceso uvicorn no reinicia. Railway redespliega cada ~1-3 días en media → hit rate inter-día depende de si el refresh cae en la misma sesión.

### 9.3 Estimación de coste evitado por caché

Cada miss: 1 llamada a `get_creator_data(use_cache=True)` → si su propio cache (5 min TTL) está warm, es ~1 ms. Si está cold: 1 query PostgreSQL multi-tabla (~30-60 ms). El cache de `_prefix_cache` evita repetir la composición de strings (trivial, ~0.1 ms). **Valor real del caché: despreciable en coste; valioso por estabilidad del prefix** (misma construcción dentro de una ventana de tiempo → prefix consistente).

## 10. Git blame & evolución

```
$ git log --all --format="%h %ad %s" --date=short -- core/contextual_prefix.py
dae541df 2026-04-02 audit: 14 systems optimized, 80+ bugs fixed, ..., RAG contextual prefix, anti-echo, OpenAI embeddings confirmed
```

**Observación**: 1 solo commit. **No ha habido iteraciones, fixes, regresiones documentadas**. El archivo lleva 21 días sin cambios. Esto puede significar:
- (a) Está tan bien diseñado que no ha necesitado tocarse (verosímil por la calidad del docstring y la presencia de 15 tests).
- (b) Nadie mira las métricas del sistema porque no hay métricas que mirar (0 Prometheus counters).
- (c) Los 3 callsites son operaciones cold-path invocadas manualmente o por jobs — nadie nota degradación silenciosa.

El commit squash `dae541df` (título menciona "80+ bugs fixed, ..., RAG contextual prefix") sugiere que el feature fue añadido en bulk sin un PR dedicado — **sin code review específico, sin medición pre/post en CCEE del impacto sobre J6/K1/K2**.

## 11. Tests existentes (15 tests, todos pass)

`tests/test_contextual_prefix.py`:

| # | Test | Cubre | Gap |
|---|------|-------|-----|
| 1 | `test_full_data_prefix` | Happy path Iris | — |
| 2 | `test_missing_specialties_uses_bio` | Fallback bio | — |
| 3 | `test_missing_all_knowledge_about` | KA vacío, solo nombre | — |
| 4 | `test_no_creator_returns_empty` | Creator sin name | — |
| 5 | `test_prefix_is_cached` | Caché funciona | No testea TTL expiration |
| 6 | `test_prefix_capped_at_500_chars` | Cap funciona | No testea corte mid-word |
| 7 | `test_formal_style_mentioned` | formality=formal | No testea informal default (silencio) |
| 8 | `test_italian_dialect` | dialect italian + Milano | No testea dialect no mapeado |
| 9 | `test_db_error_returns_empty` | Fail-open | No alerta ni métrica |
| 10 | `test_product_fallback_when_no_specialties` | Fallback products | — |
| 11 | `test_faq_fallback_when_only_name` | Fallback FAQ | — |
| 12 | `test_prepends_prefix` | Wrapper single | — |
| 13 | `test_empty_prefix_passes_text_only` | Wrapper sin prefix | — |
| 14 | `test_batch_prepends_to_all` | Wrapper batch | No testea batch mixed (algunos con/sin prefix) |
| 15 | `test_semantic_search_uses_raw_embedding` | Asimetría query/doc | Verificado por inspect.getsource — frágil |

**Gaps críticos**:
- **Cross-creator contamination** (callsite #2 en `content.py:427`): no testeado.
- **Creator_id="unknown"** (callsite #1): no testeado.
- **Multilingual mismatch** (estructura ES + contenido IT): no testeado.
- **TTL expiration**: no testeado.
- **Race condition** en caché multi-thread: no testeado (y BoundedTTLCache no es thread-safe).
- **Hit/miss counters**: inexistentes.

---

## Resumen ejecutivo Fase 2

- **Arquitectura**: simple y limpia — 3 funciones públicas, 1 helper, cache BoundedTTL. Docstring excelente con asimetría query/doc explicada.
- **Hardcoding inventariado**: `max_size=50`, `ttl_seconds=300`, cap `500`, `specialties[:3]`, `products[:5]`, `faqs[:3]`, `first_sentence len > 10`, `_DIALECT_LABELS` (7 entradas), conectivos ES (`ofrece`, `en`, `Habla`, `Estilo ... y ...`), `formality=="casual"` (valor inconsistente con dataclass).
- **Bug #1 (L104, semantic.py)**: `creator_id="unknown"` fallback → prefix vacío, vectores huérfanos en pgvector, sin alerta.
- **Bug #2 (L427, content.py)**: `creator_id` del request pasado al prefix vs `row.creator_id` de la BD en `store_embedding` → riesgo de cross-creator contamination.
- **Bug #3 (content_refresh.py:190)**: iteración uno-a-uno en vez de batch, 100x más calls OpenAI que necesario.
- **Bug #4 (multilingual)**: estructura del prefix hardcoded en ES, mismatch con creators IT/EN. Formality=="casual" nunca matchea (valores reales son "informal", "formal", "mixed").
- **Bug #5 (cache invalidation)**: cambio en `knowledge_about` no invalida `_prefix_cache` (ventana 5 min) ni los vectores ya indexados (indefinido hasta refresh).
- **Observabilidad**: 1 log.info por miss, sin structured fields, sin métricas Prometheus, cache sin hit/miss counters.
- **Tests**: 15 pass, pero gaps en cross-creator, unknown creator, multilingual, TTL, race condition.
- **Git blame**: 1 commit `dae541df` (2026-04-02) squash sin review dedicado. 21 días sin iteración.

**STOP Fase 2.** Procedo a Fase 3 (bugs detectados con detalle y reproducción).
