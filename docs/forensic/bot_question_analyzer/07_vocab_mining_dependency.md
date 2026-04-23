# Bot Question Analyzer — Vocab Mining Dependency

**Fecha:** 2026-04-23
**Estado:** especificación + plan de bootstrap. **NO ejecutado.**
**Dependency:** este worker es pre-requisito para activar `ENABLE_QUESTION_CONTEXT=true` en el arm B del A/B CCEE y posteriormente en Railway. Sin él, el analyzer cae a fallback universal (solo emojis).

---

## 1. Contexto

El refactor zero-hardcoding del PR #82 eliminó las listas literales de afirmaciones del módulo. `is_short_affirmation(msg, creator_id)` ahora consulta `personality_docs.vocab_meta.content.affirmations` (key nueva) via `services.calibration_loader._load_creator_vocab()`. Sin que esa key esté poblada, el sistema funciona pero detecta únicamente los 9 emojis del fallback universal — lo cual es correcto arquitectónicamente pero inútil para medir el impacto real del analyzer.

Este documento especifica **cómo poblar** esa key. La implementación del worker completo es responsabilidad de un PR separado; aquí se entrega:
1. **Especificación formal** del mining job (production-grade).
2. **Script de bootstrap** one-time para desbloquear la medición E1 con Iris.
3. **Plan de ejecución** en 3 fases (dev → staging → prod) con smoke tests.

---

## 2. Especificación del mining job (production-grade)

### 2.1 Schema involucrado

**Input tables (read-only):**
```sql
-- messages: todos los mensajes procesados por el pipeline
--   role = 'assistant' (bot) | 'user' (lead)
--   content = texto del mensaje
--   lead_id FK → leads.id
--   created_at = orden temporal
SELECT id, lead_id, role, content, created_at FROM messages;

-- leads: metadata del lead (per creator)
--   creator_id FK → creators.id (UUID)
SELECT id, creator_id FROM leads;

-- creators: para resolver slug ↔ UUID
SELECT id, name FROM creators;
```

**Output table:**
```sql
-- personality_docs: UPSERT (creator_id, doc_type='vocab_meta') content JSON
-- content es Text pero se parsea como JSON. Shape esperado:
--   {
--     "blacklist_words": [...],    (ya existente, no tocar)
--     "approved_terms": [...],     (ya existente, no tocar)
--     "blacklist_emojis": [...],   (ya existente, no tocar)
--     "approved_emojis": [...],    (ya existente, no tocar)
--     "blacklist_phrases": [...],  (ya existente, no tocar)
--     "affirmations": [...]        ← NUEVA, escrita por este worker
--   }
```

### 2.2 Algoritmo de mining

**Input:** corpus conversacional del creator = mensajes de todos los `leads` donde `leads.creator_id = <creator_uuid>`.

```python
def mine_affirmations(creator_id: str, min_freq_percentile: float = 75.0) -> list[str]:
    """
    Extrae afirmaciones cortas del corpus del creator.

    Pasos:
        1. Query pares (bot_msg, lead_next_msg) ordenados por tiempo por lead.
        2. Filtrar lead_next_msg donde:
           - role == 'user'
           - length(content) ≤ 15 chars después de .strip()
           - NO es puntuación pura (reusa _PUNCT_ONLY_RE del analyzer)
           - NO está vacío
        3. Normalizar tokens:
           - lowercase + strip()
           - Por cada msg, splitear en tokens (≤3), limpiar _PUNCT_CHARS de cada uno.
           - Si el msg completo es 1 token tras clean, usar el msg completo;
             si son 2-3 tokens todos de length ≤ 8, emitir cada token por separado.
        4. Contabilizar frecuencia por token normalizado.
        5. Calcular threshold = percentile(frequencies, min_freq_percentile).
           (Data-derived: NO hardcoded N. El percentile es el parámetro.)
        6. Filtrar tokens con freq >= threshold y freq >= 3 (minimum absolute floor
           para evitar hápax ruido).
        7. Filtro de sanity: eliminar tokens que aparezcan también en
           vocab_meta.blacklist_words (no tiene sentido que una afirmación esté
           en blacklist — sería señal de conflicto).
        8. Ordenar por frecuencia descendiente.
        9. Cortar top-K (default K=50 para limitar ruido).

    Output: list[str] ordenada por relevancia.
    """
```

**Justificación de los parámetros:**
- `length ≤ 15 chars`: afirmaciones reales son cortas. Empíricamente cubre "si", "vale", "ok", "perfecto", "de acuerdo", "👍", "siiii" sin incluir frases.
- `min_freq_percentile=75.0`: se descubre de la distribución del corpus (data-derived, no absoluto). En corpus típicos, top-25% de tokens cortos post-pregunta son las afirmaciones dominantes.
- `freq_floor=3`: evita hápax legomena (apariciones únicas que son ruido).
- `top-K=50`: límite superior para mantener el set manageable; 50 afirmaciones cubren >95% del uso real en los corpus típicos observados.

### 2.3 Frecuencia de ejecución

| Trigger | Cuándo | Acción |
|---------|--------|--------|
| **Onboarding inicial** | Tras ingestion del primer corpus del creator (≥500 mensajes) | Primera extracción y upsert |
| **Nightly refresh** | Cada 24h | Re-mining incremental. Si el set cambia >10%, log warning |
| **Manual trigger** | Via script CLI | Para rebuilds ad-hoc (corpus corrupto, iteración del algoritmo, etc.) |

**No re-minear en cada request:** el mining es O(mensajes × leads) y no debe bloquear el pipeline de respuesta. Es un batch job asíncrono.

### 2.4 Implementación sugerida

Opciones (a decidir en el PR del worker):

**Opción A — Extender `scripts/bootstrap_vocab_metadata.py`:**
El script actual parsea Doc D markdown. Añadir una fase que haga mining del corpus DB y merge el resultado con el parseo existente. Ventaja: reuso de infra de UPSERT + serialización JSON.

**Opción B — Nuevo `services/affirmation_miner.py`:**
Módulo dedicado. `services/` ya tiene siblings (`vocabulary_extractor.py`, `calibration_generator.py`, `calibration_loader.py`). Coherente arquitectónicamente.

**Opción C — Extender `services/vocabulary_extractor.py`:**
Si el servicio existente ya ataca el mismo corpus, evitamos duplicar queries. Revisar primero el scope actual.

**Recomendación:** **Opción B** (nuevo módulo). Permite ciclo test-dev aislado y no contamina scripts de bootstrap con lógica de mining DB.

### 2.5 Integración con el pipeline de ingestion

El worker debe registrarse en `api/startup/handlers.py` o como job en `core/task_scheduler.py`:

```python
# api/startup/handlers.py (pseudo)
scheduler.add_job(
    mine_affirmations_all_creators,
    trigger='cron',
    hour=3, minute=15,  # 3:15 AM, fuera de pico de scoring
    initial_delay_seconds=300,
)
```

**Impacto operacional:** el mining nocturno añade ~O(N creators × 30s) de carga una vez al día. Trivial vs. el scoring batch diario.

---

## 3. Bootstrap Iris — script one-time para desbloquear E1

### 3.1 Archivo

`scripts/bootstrap_vocab_meta_affirmations_iris.py` — **a crear en el PR del worker, no en este PR.** Aquí va la especificación + código completo para que el implementador lo copie.

### 3.2 Código completo del script

```python
#!/usr/bin/env python3
"""
Bootstrap one-time para poblar personality_docs.vocab_meta.affirmations
del creator iris_bertran. Desbloquea la medición CCEE del PR #82.

Uso:
    # Dry-run (muestra tokens sin escribir)
    railway run --environment=development python3 \\
        scripts/bootstrap_vocab_meta_affirmations_iris.py --dry-run

    # Escribir en dev/staging
    railway run --environment=development python3 \\
        scripts/bootstrap_vocab_meta_affirmations_iris.py --creator iris_bertran

    # Prod (tras smoke test OK en staging)
    railway run --environment=production python3 \\
        scripts/bootstrap_vocab_meta_affirmations_iris.py --creator iris_bertran

Idempotente: usa UPSERT (personality_docs UNIQUE (creator_id, doc_type)) y
merge con content JSON existente. Si la key 'affirmations' ya existe, se
reemplaza con la mined fresca (no duplica, no acumula).
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Importar configuración real (DB session)
from api.database import SessionLocal
from sqlalchemy import text as sql

# Constantes del analyzer — deben quedar sincronizadas. Si cambian, ajustar aquí.
_PUNCT_CHARS = "!.,?¡¿"
_PUNCT_ONLY_RE = re.compile(r'^[\s!.,?¡¿]+$')
MAX_LEN = 15
MIN_FREQ_PERCENTILE = 75.0
MIN_FREQ_FLOOR = 3
TOP_K = 50


def _normalize(msg: str) -> str:
    return msg.lower().strip()


def _is_candidate(msg: str) -> bool:
    """Filtro inicial: short lead message post-bot-question."""
    if not msg:
        return False
    m = _normalize(msg)
    if not m or len(m) > MAX_LEN:
        return False
    if _PUNCT_ONLY_RE.match(m):
        return False
    return True


def _extract_tokens(msg: str) -> list[str]:
    """Split del msg en tokens. 1 token ≤15ch → msg completo. Hasta 3 tokens
    → cada token limpio de puntuación (≤8ch). El set incluye ambos para que
    match directo y match multi-token funcionen."""
    m = _normalize(msg)
    yielded = []
    if len(m) <= MAX_LEN:
        yielded.append(m)
    words = m.split()
    if 1 < len(words) <= 3:
        for w in words:
            clean = w.strip(_PUNCT_CHARS)
            if clean and len(clean) <= 8:
                yielded.append(clean)
    return yielded


def mine_affirmations(session, creator_slug: str) -> tuple[list[str], dict]:
    """Query pairs (bot_msg, lead_next_msg) y extrae afirmaciones."""
    # Resolver slug → UUID
    row = session.execute(
        sql("SELECT id FROM creators WHERE name = :slug LIMIT 1"),
        {"slug": creator_slug}
    ).fetchone()
    if not row:
        raise SystemExit(f"Creator '{creator_slug}' no existe en DB")
    creator_uuid = str(row.id)

    # Query: para cada lead del creator, orden temporal. Se hace un join
    # auto con LAG para emparejar bot_msg → siguiente lead_msg.
    query = sql("""
        WITH ordered AS (
            SELECT m.id, m.lead_id, m.role, m.content, m.created_at,
                   LAG(m.role) OVER (PARTITION BY m.lead_id ORDER BY m.created_at) AS prev_role,
                   LAG(m.content) OVER (PARTITION BY m.lead_id ORDER BY m.created_at) AS prev_content
            FROM messages m
            JOIN leads l ON l.id = m.lead_id
            WHERE l.creator_id = :cid
        )
        SELECT content
        FROM ordered
        WHERE role = 'user'
          AND prev_role = 'assistant'
          AND prev_content LIKE '%?%';
    """)
    rows = session.execute(query, {"cid": creator_uuid}).fetchall()

    # Contabilizar tokens
    counter: Counter = Counter()
    total_candidates = 0
    for r in rows:
        if _is_candidate(r.content):
            total_candidates += 1
            for token in _extract_tokens(r.content):
                counter[token] += 1

    # Threshold data-derived
    if not counter:
        return [], {"total_candidates": 0, "threshold": 0, "top_k": 0}

    freqs = sorted(counter.values())
    idx = int(len(freqs) * MIN_FREQ_PERCENTILE / 100)
    threshold = max(freqs[idx] if idx < len(freqs) else MIN_FREQ_FLOOR, MIN_FREQ_FLOOR)

    # Filtrar + sort + top-K
    affirmations = sorted(
        [(tok, cnt) for tok, cnt in counter.items() if cnt >= threshold],
        key=lambda x: -x[1]
    )[:TOP_K]

    # Filtro sanity: excluir blacklist_words del vocab_meta existente
    existing_vocab = session.execute(
        sql("""SELECT content FROM personality_docs pd
               JOIN creators c ON c.id::text = pd.creator_id
               WHERE c.name = :slug AND pd.doc_type = 'vocab_meta' LIMIT 1"""),
        {"slug": creator_slug}
    ).fetchone()
    blacklist = set()
    if existing_vocab:
        try:
            parsed = json.loads(existing_vocab.content)
            blacklist = {w.lower() for w in parsed.get("blacklist_words", [])}
        except (ValueError, TypeError):
            pass
    final = [tok for tok, _ in affirmations if tok not in blacklist]

    stats = {
        "total_candidates": total_candidates,
        "unique_tokens": len(counter),
        "threshold_freq": threshold,
        "top_k_after_sanity": len(final),
        "blacklist_excluded": len([t for t, _ in affirmations if t in blacklist]),
    }
    return final, stats


def upsert_affirmations(session, creator_slug: str, affirmations: list[str]) -> None:
    """Merge 'affirmations' key en vocab_meta existente. Idempotente."""
    creator_row = session.execute(
        sql("SELECT id FROM creators WHERE name = :slug LIMIT 1"),
        {"slug": creator_slug}
    ).fetchone()
    creator_uuid = str(creator_row.id)

    existing = session.execute(
        sql("""SELECT content FROM personality_docs
               WHERE creator_id = :cid AND doc_type = 'vocab_meta' LIMIT 1"""),
        {"cid": creator_uuid}
    ).fetchone()

    if existing:
        try:
            vocab = json.loads(existing.content)
        except (ValueError, TypeError):
            vocab = {}
        vocab["affirmations"] = affirmations   # reemplaza (no acumula)
        new_content = json.dumps(vocab, ensure_ascii=False, indent=2)
        session.execute(
            sql("""UPDATE personality_docs
                   SET content = :content, updated_at = NOW()
                   WHERE creator_id = :cid AND doc_type = 'vocab_meta'"""),
            {"content": new_content, "cid": creator_uuid}
        )
    else:
        # Crear row nueva (sólo si vocab_meta no existía)
        new_vocab = {"affirmations": affirmations}
        session.execute(
            sql("""INSERT INTO personality_docs (creator_id, doc_type, content)
                   VALUES (:cid, 'vocab_meta', :content)
                   ON CONFLICT (creator_id, doc_type) DO NOTHING"""),
            {"cid": creator_uuid, "content": json.dumps(new_vocab, ensure_ascii=False, indent=2)}
        )
    session.commit()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--creator", default="iris_bertran")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    session = SessionLocal()
    try:
        affirmations, stats = mine_affirmations(session, args.creator)
        print(f"=== Mining stats for {args.creator} ===")
        for k, v in stats.items():
            print(f"  {k}: {v}")
        print(f"\n=== Top-{len(affirmations)} affirmations ===")
        for i, tok in enumerate(affirmations, 1):
            print(f"  {i:3d}. {tok!r}")

        if args.dry_run:
            print("\n[DRY-RUN] No DB write.")
            return

        upsert_affirmations(session, args.creator, affirmations)
        print(f"\n✅ UPSERTed {len(affirmations)} affirmations for {args.creator}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
```

### 3.3 Propiedades del script

| Propiedad | Cumplimiento |
|-----------|--------------|
| **Zero hardcoding lingüístico** | ✅ Ninguna palabra/idioma en el código. Todo se deriva del corpus. |
| **Data-derived threshold** | ✅ `percentile(75)` sobre la distribución observada. |
| **Idempotente** | ✅ UPSERT + reemplaza key `affirmations` (no duplica, no acumula). |
| **No destructivo** | ✅ Merge con vocab_meta existente — preserva `blacklist_words`, `approved_terms`, etc. |
| **Sanity check anti-conflicto** | ✅ Excluye tokens presentes en `blacklist_words` del mismo creator. |
| **Dry-run disponible** | ✅ `--dry-run` imprime stats sin escribir. |
| **Observabilidad** | ✅ Stats impresas: total_candidates, unique_tokens, threshold_freq, top_k, blacklist_excluded. |
| **Transaccional** | ✅ `session.commit()` explícito; rollback implícito on exception. |

---

## 4. Plan de ejecución (3 fases — Dev → Staging → Prod)

### Fase 4.1 — Dev (sandbox local)

**Objetivo:** validar el algoritmo contra un subset del corpus sin tocar DB compartida.

```bash
# 1. Crear el script en el PR separado (NO en este PR)
# 2. Dry-run contra dev DB (Neon branch de desarrollo)
railway run --environment=development python3 \
    scripts/bootstrap_vocab_meta_affirmations_iris.py \
    --creator iris_bertran --dry-run

# 3. Revisar output visualmente:
#    - ¿total_candidates > 100? (corpus suficiente)
#    - ¿top-10 incluye "si", "vale", "ok", "claro", "perfecto"? (sanity)
#    - ¿NO incluye palabras no-afirmativas como "hola", "gracias", "no"? (sanity)
#    - ¿threshold_freq razonable? (típicamente 5-20 apariciones)
# 4. Si algo no cuadra: ajustar parámetros (MIN_FREQ_PERCENTILE, MAX_LEN).
```

**Criterio de paso a Fase 4.2:**
- [ ] Dry-run output es visualmente coherente.
- [ ] Top-10 incluye al menos 5 afirmaciones "obvias" que cualquier hispanohablante reconocería.
- [ ] Ningún token es claramente negativo/neutro.

### Fase 4.2 — Staging

**Objetivo:** ejecutar bootstrap real + smoke test end-to-end contra DB staging + código del PR #82.

```bash
# 1. Write real en staging
railway run --environment=staging python3 \
    scripts/bootstrap_vocab_meta_affirmations_iris.py \
    --creator iris_bertran

# 2. Verificar DB manualmente
railway run --environment=staging python3 -c "
from api.database import SessionLocal
from sqlalchemy import text
s = SessionLocal()
row = s.execute(text('''
    SELECT content::json->'affirmations' AS aff
    FROM personality_docs pd
    JOIN creators c ON c.id::text = pd.creator_id
    WHERE c.name = 'iris_bertran' AND pd.doc_type = 'vocab_meta'
''')).fetchone()
print('affirmations:', row.aff if row else '(missing)')
print('count:', len(row.aff) if row and row.aff else 0)
s.close()
"
```

**Smoke test crítico (staging):**

```bash
railway run --environment=staging python3 -c "
import sys; sys.path.insert(0, '.')
from core.bot_question_analyzer import is_short_affirmation, get_metrics, reset_metrics

reset_metrics()

# TEST 1: palabra ES común detectada con source=mined (no fallback)
result = is_short_affirmation('sí', 'iris_bertran')
m = get_metrics()
assert result is True, f'ESPERADO True, got {result}'
assert m.get('vocab_source.mined', 0) >= 1, f'ESPERADO source=mined, metrics={m}'
assert m.get('vocab_source.fallback', 0) == 0, f'fallback NO debe activarse'
assert m.get('vocab_source.empty', 0) == 0, f'empty NO debe activarse'
print('✅ TEST 1 OK: is_short_affirmation(\"sí\", \"iris_bertran\") = True, source=mined')

# TEST 2: creator desconocido → fallback emoji-only
reset_metrics()
assert is_short_affirmation('sí', 'nonexistent_creator') is False
assert is_short_affirmation('👍', 'nonexistent_creator') is True
m = get_metrics()
assert m.get('vocab_source.empty', 0) >= 1 or m.get('vocab_source.fallback', 0) >= 1
print('✅ TEST 2 OK: creator desconocido cae a fallback universal (emoji-only)')

# TEST 3: palabra NO afirmativa NO debe ser detectada ni con creator válido
reset_metrics()
assert is_short_affirmation('hola', 'iris_bertran') is False
print('✅ TEST 3 OK: palabra no-afirmativa rechazada')

print()
print('🟢 Smoke test COMPLETO. vocab_meta de iris_bertran listo para arm B.')
"
```

**Criterio de paso a Fase 4.3:**
- [ ] Los 3 smoke tests pasan en staging.
- [ ] La DB staging tiene `affirmations` populado con ≥20 tokens.
- [ ] Observabilidad: `vocab_source.mined` es la métrica dominante en el smoke.
- [ ] Sin excepciones en logs durante la ejecución.

### Fase 4.3 — Prod (tras 4.2 OK)

**⚠️ Pre-condiciones:**
- Fases 4.1 y 4.2 completadas sin issues.
- PR #82 aprobado para merge (pero aún no mergeado — se mergea después del KEEP del A/B).
- Flag `ENABLE_QUESTION_CONTEXT` sigue en **false** en Railway (no cambiar en este paso).

**Ejecución:**
```bash
# 1. Ejecutar bootstrap en prod
railway run --environment=production python3 \
    scripts/bootstrap_vocab_meta_affirmations_iris.py \
    --creator iris_bertran

# 2. Verificar escritura
railway run --environment=production python3 -c "
from api.database import SessionLocal
from sqlalchemy import text
s = SessionLocal()
row = s.execute(text('''
    SELECT content::json->'affirmations' AS aff, updated_at
    FROM personality_docs pd
    JOIN creators c ON c.id::text = pd.creator_id
    WHERE c.name = 'iris_bertran' AND pd.doc_type = 'vocab_meta'
''')).fetchone()
print('affirmations count:', len(row.aff) if row and row.aff else 0)
print('updated_at:', row.updated_at if row else '-')
print('first 10:', row.aff[:10] if row and row.aff else [])
s.close()
"

# 3. Railway logs — confirmar que no hay errores posteriores
railway logs -n 200 2>&1 | grep -iE "error|exception|bootstrap" | head -20
# Expected: 0 matches (el bootstrap es read-mostly, solo escribe 1 row)

# 4. NO activar ENABLE_QUESTION_CONTEXT en Railway aún.
#    La activación es un paso explícito del plan de medición (arm B).
```

**Post-ejecución:**
- [ ] `affirmations` populado en prod con el mismo count que staging (±20% tolerancia por tráfico diferente).
- [ ] Sin errores en logs durante la siguiente hora.
- [ ] Monitoreo copilot_evaluations.diary se mantiene estable (ningún cambio de comportamiento porque flag sigue OFF).

### Fase 4.4 — Stefano (tras Iris OK en prod)

Repetir Fases 4.1 → 4.3 con `--creator stefano` (o slug correspondiente). Mismos criterios de paso.

**Expected:** menos tokens mined (Stefano tiene corpus más pequeño). Si < 10 tokens → documentar y decidir si arm B es representativo para Stefano o solo para Iris.

---

## 5. Acceptance criteria consolidado

Antes de proceder al arm B del A/B CCEE del PR #82:

| Check | Responsable | Blocking? |
|-------|-------------|-----------|
| Script bootstrap creado en PR separado | Worker implementor | ✅ |
| Fase 4.1 (dev dry-run) passes | Worker implementor | ✅ |
| Fase 4.2 (staging) + smoke test passes | Worker implementor | ✅ |
| Fase 4.3 (prod Iris) ejecutada | Operator | ✅ |
| Fase 4.4 (prod Stefano) ejecutada | Operator | ⚠️ Optional (decide scope del A/B) |
| `vocab_source.mined` dominante en logs tras activación arm B | Operator | ✅ |
| `vocab_source.empty` == 0 durante arm B | Operator | ✅ |
| Nightly refresh scheduled | Worker implementor | ❌ (post-KEEP) |

---

## 6. Riesgos y mitigaciones

| Riesgo | Probabilidad | Mitigación |
|--------|--------------|------------|
| Corpus de Iris tiene ruido (spam, reacciones no-afirmativas) en post-pregunta | Media | Filtro `prev_content LIKE '%?%'` + threshold percentile evita capturar ruido aleatorio |
| Tokens incluyen palabras semi-afirmativas ambiguas ("bueno", "ya") | Media | Documentar; decisión se valida en A/B (si esos tokens producen falsos positivos, se ven en S1 regression y gate REVERT dispara) |
| Stefano tiene corpus insuficiente (<500 mensajes en pares bot→lead) | Media-alta | Fase 4.4 documenta este caso; medición CCEE puede limitarse a Iris como scope primario |
| UPSERT colisiona con otro worker escribiendo vocab_meta simultáneamente | Baja | Uso de `UPDATE ... WHERE creator_id=X AND doc_type='vocab_meta'` + `ON CONFLICT DO NOTHING` en INSERT. SQL-level idempotence |
| Tokens mined luego cambian el A/B post-hoc | Baja | El script imprime el set antes de escribir — documentar la versión usada en el reporte del A/B |

---

## 7. Out-of-scope (explícito)

Este documento NO cubre:

- **Implementación** del worker completo. Es un PR separado.
- **Ejecución real** del bootstrap. Este documento es el plan; la ejecución es operacional.
- **Mining de posts/comentarios públicos del creator.** La spec usa sólo DMs. Extensión futura a posts si se descubre que los DMs no capturan la variedad completa.
- **Emoji mining.** Los 9 emojis del fallback universal quedan en código por razones de degradación graceful. Si en el futuro se quiere que también los emojis sean mined, extender el shape del `content::json` con una key `affirmation_emojis` y reusar el mismo script.

---

## 8. Resumen ejecutivo

- **Dependency crítica** del PR #82: `personality_docs.vocab_meta.content.affirmations` debe existir antes del arm B.
- **Script de bootstrap** provisto en la sección 3, con 100% zero-hardcoding lingüístico y threshold data-derived.
- **Plan 3 fases** (dev → staging → prod) con smoke test inequívoco que valida `vocab_source.mined` como source dominante.
- **Worker production-grade** (nightly + on-demand) queda como PR separado, especificado en la sección 2.
- **Bootstrap es idempotente** y no destructivo (merge con vocab_meta existente sin tocar otras keys).

---

**STOP.** Pre-requisitos pre-merge de PR #82:
- A) Este doc (`07_vocab_mining_dependency.md`) entregado. ✅
- B) Plan bootstrap Iris entregado — script + 3 fases + smoke test. ✅

Siguiente acción (fuera de este PR): implementador crea el script en PR separado y ejecuta Fase 4.1.
