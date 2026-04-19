# Requirements Audit — 2026-04-19

**Autor:** Worker J (ops audit)
**Trigger:** Bug cachetools — 3 cache-bust episodes en un solo día
**Branch:** feature/ops-requirements-audit

---

## 1. Contexto: El bug del día

El 2026-04-19 tuvimos 3 episodios de cache-bust forzado en Railway porque `cachetools` no estaba en `requirements-lite.txt` (el fichero que usa el Dockerfile). El prod container arrancaba sin `TTLCache` → `ImportError` en runtime → restart loop.

**Root cause:** Dos ficheros de requirements divergieron silenciosamente. El Dockerfile usa `requirements-lite.txt`; los desarrolladores instalan con `requirements.txt`. Cada vez que se añade un dep a `requirements.txt` y se olvida añadirlo a `requirements-lite.txt`, hay un bug latente en prod.

**Fix de hoy:** `cachetools>=5.3.0,<6.0.0` añadido a `requirements-lite.txt` (commit a592f66b).

**Este audit:** encontrar todos los demás bugs similares antes de que exploten.

---

## 2. Ficheros analizados

| Fichero | Propósito |
|---------|-----------|
| `requirements.txt` | Full local dev deps |
| `requirements-lite.txt` | **Usado por Dockerfile** — imagen prod |
| `Dockerfile` | `COPY requirements-lite.txt . && pip install -r requirements-lite.txt` |
| `scripts/start.sh:96` | `alembic upgrade head && uvicorn ...` — corre en el container |

---

## 3. Análisis completo

### 3.1 Packages SOLO en requirements.txt (candidatos a bug)

| Package | Imports en prod? | Archivos | Veredicto |
|---------|-----------------|---------|-----------|
| `alembic>=1.13.0` | ✅ CLI en `scripts/start.sh:96` (`alembic upgrade head`) | `start.sh`, `api/routers/maintenance.py` (SQL query) | **BUG — AÑADIR A LITE** |
| `feedparser>=6.0.0` | ✅ `ingestion/podcast_connector.py:139` (lazy import) | Llamado desde `api/routers/ingestion_v2/` | **BUG — AÑADIR A LITE** |
| `readability-lxml>=0.8.1` | ✅ `ingestion/content_extractor.py:43` (lazy import) | Llamado desde `api/routers/ingestion_v2/debug.py` | **BUG — AÑADIR A LITE** |
| `yt-dlp>=2024.1.0` | ✅ `ingestion/youtube_connector.py:121,281,344` (lazy) | Llamado desde `api/routers/ingestion_v2/youtube.py` | **BUG — AÑADIR A LITE** |
| `youtube-transcript-api>=0.6.0` | ✅ `ingestion/youtube_connector.py:215` (lazy) | Mismo path que yt-dlp | **BUG — AÑADIR A LITE** |
| `pypdf>=4.0.0` | ✅ `ingestion/pdf_extractor.py:139,178,188` (lazy) | Llamado desde `api/routers/ingestion_v2/` | **BUG — AÑADIR A LITE** |
| `langdetect>=1.0.9` | ✅ `core/frustration_detector.py:432` + `services/calibration_loader.py:479` | **PROD CORE** — no es ingestion | **BUG CRÍTICO — AÑADIR A LITE** |
| `streamlit>=1.28.0` | ❌ No imports en core/, services/, api/ | Solo scripts/dashboards | **DEV-ONLY — NO añadir a lite** |
| `pytest-cov>=4.0.0` | ❌ No imports en prod | Solo testing | **DEV-ONLY — NO añadir a lite** |

### 3.2 Packages SOLO en requirements-lite.txt

| Package | En requirements.txt? | Veredicto |
|---------|---------------------|-----------|
| `instaloader>=4.10.0` | ❌ Missing | `core/auto_configurator.py:664` — **AÑADIR A requirements.txt para consistencia** |

Note: `instaloader` aparecía duplicado en `requirements-lite.txt` — duplicado eliminado.

### 3.3 Packages en AMBOS con versiones diferentes

| Package | requirements.txt | requirements-lite.txt | Ganador | Razón |
|---------|-----------------|----------------------|---------|-------|
| `uvicorn` | `>=0.24.0` | `==0.32.1` | **lite gana** | Prod usa versión fija probada |
| `tenacity` | `>=8.2.0` (+ duplicado) | `>=8.0.0` | **>=8.2.0** | Más restrictivo, probado; lite actualizado |
| `httpx` | `>=0.25.0` | `>=0.25.0` | ✅ Igual | |

### 3.4 Duplicados eliminados

| Fichero | Entrada duplicada | Acción |
|---------|------------------|--------|
| `requirements.txt` | `tenacity>=8.2.0` (líneas 36 y 46) | Conservada 1 entrada |
| `requirements.txt` | `sentry-sdk[fastapi]>=1.39.0` (líneas 63 y 71) | Conservada 1 entrada |
| `requirements-lite.txt` | `instaloader>=4.10.0` (líneas 29 y 39) | Conservada 1 entrada |

---

## 4. Cambios aplicados

### 4.1 requirements-lite.txt — 7 packages añadidos, 1 duplicado eliminado, tenacity bumped

```diff
+ alembic>=1.13.0           # scripts/start.sh runs `alembic upgrade head`
+ feedparser>=6.0.0         # ingestion/podcast_connector.py
+ readability-lxml>=0.8.1   # ingestion/content_extractor.py
+ yt-dlp>=2024.1.0          # ingestion/youtube_connector.py
+ youtube-transcript-api>=0.6.0  # ingestion/youtube_connector.py
+ pypdf>=4.0.0              # ingestion/pdf_extractor.py
+ langdetect>=1.0.9         # core/frustration_detector.py + services/calibration_loader.py
- instaloader>=4.10.0       # (duplicate removed, first entry kept)
~ tenacity>=8.0.0 → >=8.2.0 # aligned with requirements.txt
```

### 4.2 requirements.txt — duplicados eliminados, instaloader añadido

```diff
+ instaloader>=4.10.0       # core/auto_configurator.py (was only in lite)
- tenacity>=8.2.0           # duplicate removed (kept first occurrence)
- sentry-sdk[fastapi]>=1.39.0  # duplicate removed (kept first occurrence)
```

### 4.3 requirements-dev.txt — creado

Nuevo fichero `requirements-dev.txt` para deps solo de desarrollo:
- `pytest-cov>=4.0.0`
- `streamlit>=1.28.0`

```bash
# Uso local:
pip install -r requirements-dev.txt
```

---

## 5. Por qué los imports en `ingestion/` son bugs prod

Los imports lazy (dentro de funciones) en `ingestion/` no fallan al importar el módulo, sino al llamar la función. En prod:

- `api/routers/ingestion_v2/youtube.py:85` → `ingestion.v2.youtube_ingestion` → `ingestion.youtube_connector` → `import yt_dlp` → **ImportError en runtime** si no está instalado
- `api/routers/ingestion_v2/debug.py:69` → `ingestion.deterministic_scraper` → `ingestion.content_extractor` → `from readability import Document` → **ImportError en runtime**
- `api/routers/oauth/instagram.py:853` → `ingestion.transcriber` — cadena de imports
- `core/frustration_detector.py:432` → `from langdetect import detect_langs` → **ImportError** cada vez que el detector procesa un mensaje bilingüe

Todos estos son bugs silenciosos: el servidor arranca sin errores, pero falla cuando el código path se ejecuta por primera vez.

---

## 6. Verificación post-cambio

```bash
# Dry-run sin conflictos
pip install --dry-run -r requirements-lite.txt  # ✅ OK

# Imports críticos
python3.11 -c "from cachetools import TTLCache; print('cachetools OK')"       # ✅
python3.11 -c "from core.generation.circuit_breaker import CircuitBreaker"    # ✅
python3.11 -c "import langdetect; print('langdetect OK')"                     # ✅

# Smoke tests: 7/7 passed (3 skipped — no DATABASE_URL local)
```

---

## 7. Recomendaciones futuras

### Recomendación 1 (inmediata): CI check de consistencia

Añadir a GitHub Actions un check que detecte imports en prod paths no cubiertos por `requirements-lite.txt`:

```yaml
# .github/workflows/requirements_check.yml
- name: Check requirements consistency
  run: |
    # Packages in requirements.txt but not in requirements-lite.txt
    python scripts/check_requirements_consistency.py
```

O más simple: un script que normaliza ambos ficheros y verifica que `requirements-lite.txt` contiene un superset de los packages que aparecen en imports de `core/`, `services/`, `api/`, `ingestion/`.

### Recomendación 2 (próximo sprint): Consolidar a un solo fichero

El patrón ideal es:

```
requirements.txt (prod) = lo que va en el Dockerfile
requirements-dev.txt = -r requirements.txt + dev extras
```

Esto elimina la discrepancia por diseño. El Dockerfile pasaría a usar `requirements.txt` directamente. El nombre "lite" ya no tendría sentido.

**Precaución:** Este cambio requiere revisar que `requirements.txt` no tenga deps innecesariamente pesadas para prod (ej. `sentence-transformers` ya está en lite, así que está OK).

### Recomendación 3: Añadir comentario a Dockerfile

```dockerfile
# requirements-lite.txt = prod-only deps.
# See docs/ops/requirements_audit_2026_04_19.md for consistency rules.
COPY requirements-lite.txt .
```

### Runbook: cómo añadir un nuevo package sin romper prod

1. ¿Se importa en `core/`, `services/`, `api/`, `ingestion/`? → **Añadir a requirements-lite.txt**
2. ¿Solo en `scripts/`, `tests/`? → **Solo en requirements-dev.txt**
3. Siempre añadir también a `requirements.txt` para entorno local completo
4. Verificar con `pip install --dry-run -r requirements-lite.txt` antes de push
5. Si el package usa lazy imports (`import X` dentro de una función): **sigue siendo prod dep** si la función es accesible desde la API

---

## 8. Estado post-audit

| Métrica | Antes | Después |
|---------|-------|---------|
| Packages en lite pero no en full | 1 (instaloader) | 0 |
| Packages en full con imports prod pero no en lite | 7 | 0 |
| Duplicados en requirements.txt | 2 (tenacity, sentry-sdk) | 0 |
| Duplicados en requirements-lite.txt | 1 (instaloader) | 0 |
| requirements-dev.txt | ❌ no existía | ✅ creado |
