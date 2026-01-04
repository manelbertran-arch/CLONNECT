# Notas de Migración - clonnect-memory

> Inventario de código útil identificado para migración progresiva.
> Generado: 2026-01-04

## Resumen Ejecutivo

| Funcionalidad | Archivo Origen | Fase | Estado |
|---------------|----------------|------|--------|
| Chunking con overlap | `api/main.py:83-96` | 1 | ✅ MIGRADO |
| Extracción PDF | `api/main.py:99-104` | 2 | ⏳ Pendiente |
| Transcripción audio | `api/main.py:107-117` | 2 | ⏳ Pendiente |
| PDF con fallback | `core/ingest.py:21-41` | 2 | ⏳ Pendiente |
| Transcripción GCS | `core/ingest.py:44-53` | 2 | ⏳ Pendiente |

---

## Código Encontrado para Migrar

### 1. Chunking con Overlap (FASE 1) ✅ MIGRADO

**Archivo origen:** `clonnect-memory/api/main.py`
**Líneas:** 83-96
**Función:** `split_text(text, chunk_size=1000, overlap=200)`
**Dependencias:** Ninguna (Python puro)
**Estado:** ✅ Migrado a `content_indexer.py` (2026-01-04)

**Mejoras implementadas:**
- Respeta límites de oraciones (corta en `. `, `? `, `! `, `\n`)
- Chunk size reducido a 500 (mejor para RAG)
- Overlap reducido a 50 (suficiente contexto)
- Añadido `ContentChunk` dataclass para estructurar chunks
- Añadido `create_chunks_from_content()` para crear chunks con metadata
- Añadido `generate_chunk_id()` para IDs determinísticos

**Tests:** 12 tests en `backend/tests/test_content_indexer.py`

---

### 2. Extracción de PDF (FASE 2)

**Archivo origen:** `clonnect-memory/api/main.py`
**Líneas:** 99-104
**Función:** `extract_text_from_pdf(pdf_bytes)`
**Dependencias:** `pypdf` (PdfReader)
**Estado:** ⏳ Pendiente migración Fase 2

```python
def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n\n".join(pages)
```

**Alternativa con fallback** (`core/ingest.py:21-41`):
- Soporta `pdfplumber` (mejor calidad) con fallback a `PyPDF2`
- Útil si `pypdf` falla en ciertos PDFs

---

### 3. Transcripción de Audio (FASE 2)

**Archivo origen:** `clonnect-memory/api/main.py`
**Líneas:** 107-117
**Función:** `extract_text_from_audio(audio_bytes, language_code="es-ES")`
**Dependencias:** `google-cloud-speech`
**Estado:** ⏳ Pendiente migración Fase 2

```python
def extract_text_from_audio(audio_bytes: bytes, language_code: str = "es-ES") -> str:
    client = speech.SpeechClient()
    audio = speech.RecognitionAudio(content=audio_bytes)
    config = speech.RecognitionConfig(
        language_code=language_code,
        enable_automatic_punctuation=True,
        audio_channel_count=2,
    )
    response = client.recognize(config=config, audio=audio)
    parts = [r.alternatives[0].transcript for r in response.results if r.alternatives]
    return " ".join(parts).strip()
```

**Alternativa GCS** (`core/ingest.py:44-53`):
- `transcribe_audio_gcs(gcs_uri)` para archivos ya en Cloud Storage
- Útil para audios grandes que no caben en memoria

**Notas:**
- Límite de ~1 minuto para audio síncrono
- Para audios largos, usar `long_running_recognize()`
- Considerar migrar a Whisper (OpenAI) para mejor calidad

---

### 4. Funciones Auxiliares Útiles

**Detección de tipo de archivo** (`api/main.py:120-131`):
```python
def detect_kind(filename: str, content_type: Optional[str]) -> str:
    # Detecta: pdf, txt, json, audio
```

**Creación de registros** (`api/main.py:156-167`):
```python
def make_records(chunks: List[str], source_uri: str, kind: str) -> List[Dict[str, Any]]:
    # Genera registros con id, text, source, kind, ts
```

---

## Dependencias a Añadir

### Fase 1
- Ninguna nueva (chunking es Python puro)

### Fase 2
```
pypdf>=4.0.0          # Extracción PDF
google-cloud-speech   # Transcripción audio
pdfplumber            # (opcional) Mejor extracción PDF
```

---

## Plan de Migración

### Fase 1: Chunking ✅ COMPLETADO
1. ✅ Copiar `split_text()` a `content_indexer.py`
2. ✅ Añadir tests unitarios (12 tests)
3. ⏳ Integrar con pipeline RAG existente

### Fase 2: PDF + Audio
1. Copiar `extract_text_from_pdf()` a `pdf_extractor.py`
2. Copiar `extract_text_from_audio()` a `transcriber.py`
3. Añadir dependencias a requirements.txt
4. Configurar credenciales Google Cloud
5. Añadir tests de integración

---

## NO Migrar

❌ `core/memory_core.py` - Ya existe RAG en Clonnect-creators
❌ `core/ingest.py:upload_and_ingest()` - Muy acoplado a GCS
❌ Endpoints FastAPI - Reimplementar en estructura existente

---

## Referencias

- Repo origen: `https://github.com/manelbertran-arch/clonnect-memory`
- Auditoría: `AUDITORIA_clonnect-memory.md`
- Rama de trabajo: `feature/content-ingestion-pipeline`
