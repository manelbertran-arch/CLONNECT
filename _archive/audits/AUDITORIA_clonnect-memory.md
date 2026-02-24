# 🔍 AUDITORÍA: clonnect-memory

**Fecha**: 2026-01-04
**Repositorio**: `clonnect-memory`
**Ubicación**: `/home/user/CLONNECT/clonnect-memory`
**Total de archivos de código**: 6 archivos Python

---

## 📁 1. Estructura del Repositorio

```
clonnect-memory/
├── api/
│   ├── main.py              # API FastAPI completa (388 líneas)
│   ├── core_loader_api.py   # Adapter para legacy core (57 líneas)
│   └── requirements.txt     # Dependencias
├── core/
│   ├── config.py            # Configuración GCP (9 líneas)
│   ├── memory_core.py       # Motor RAG con Vertex AI (95 líneas)
│   └── ingest.py            # Ingestión de archivos (157 líneas)
├── examples/
│   └── client_memory_api.py # Cliente de ejemplo (15 líneas)
├── infra/
│   ├── Dockerfile           # Container para Cloud Run
│   └── cloudbuild.yaml      # Deploy config
├── .gitignore
└── README.md
```

**Total**: ~720 líneas de código Python

---

## 📋 2. Inventario Detallado de Funcionalidades

### 2.1 api/main.py - API Principal

| Campo | Valor |
|-------|-------|
| **Propósito** | API completa de memoria RAG con Vertex AI |
| **Líneas** | 388 |
| **Mapeo a módulo** | #2 Content Indexer, #6 Transcriber |
| **Estado** | Completo y funcional |
| **¿Fusionado en CLONNECT?** | No |
| **Calidad** | ⭐⭐⭐⭐ |

**Clases/Funciones principales:**

```python
# EMBEDDINGS
def embed_texts(texts: List[str]) -> List[List[float]]:
    """Embeddings con Vertex AI text-embedding-004"""
    model = ensure_vertex()
    # Procesa en batches de 16
    for i in range(0, len(texts), batch_size):
        embs = model.get_embeddings(batch)

# BÚSQUEDA SEMÁNTICA
def semantic_search(query: str, top_k: int = 3) -> List[Dict[str, Any]]:
    """Búsqueda con cosine similarity en numpy"""
    qv = np.array(embed_texts([query])[0], dtype=np.float32)
    mat = np.array([it["embedding"] for it in idx], dtype=np.float32)
    qn = qv / (np.linalg.norm(qv) + 1e-8)
    mn = mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-8)
    sims = mn @ qn
    order = np.argsort(-sims)[:top_k]

# TRANSCRIPCIÓN DE AUDIO
def extract_text_from_audio(audio_bytes: bytes, language_code: str = "es-ES") -> str:
    """Transcripción con Google Cloud Speech-to-Text"""
    client = speech.SpeechClient()
    audio = speech.RecognitionAudio(content=audio_bytes)
    config = speech.RecognitionConfig(
        language_code=language_code,
        enable_automatic_punctuation=True,
        audio_channel_count=2,
    )
    response = client.recognize(config=config, audio=audio)

# EXTRACCIÓN DE PDF
def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extrae texto de PDF usando pypdf"""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    for page in reader.pages:
        pages.append(page.extract_text() or "")

# CHUNKING
def split_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
    """Divide texto en chunks con overlap"""

# ENDPOINTS
@app.post("/search")           # Búsqueda semántica
@app.post("/ingest/text")      # Ingesta texto plano
@app.post("/ingest/upload")    # Upload de archivos (PDF, audio, txt)
@app.post("/ingest/gcs")       # Ingesta desde GCS
@app.get("/health")            # Health check
@app.get("/index/stats")       # Stats del índice
```

### 2.2 core/memory_core.py - Motor RAG

| Campo | Valor |
|-------|-------|
| **Propósito** | Motor RAG con Gemini para respuestas |
| **Líneas** | 95 |
| **Mapeo a módulo** | #5 Response Engine v2 |
| **Estado** | Funcional |
| **¿Fusionado en CLONNECT?** | Parcialmente (RAG sí, Gemini no) |
| **Calidad** | ⭐⭐⭐⭐ |

**Funciones principales:**

```python
def init_memory():
    """Inicializa Vertex AI y carga índice desde GCS"""
    embed_model = TextEmbeddingModel.from_pretrained("text-embedding-004")
    gen_model = GenerativeModel("gemini-2.5-pro")

def retrieve(query: str, top_k: int = 6):
    """Recupera fragmentos relevantes con cosine similarity"""
    q_vec = np.array(embed_model.get_embeddings([query])[0].values)
    sims = (embs @ q_vec) / (embs_norm * q_norm + 1e-12)

def clonnect_answer(query: str, top_k: int = 6) -> str:
    """Genera respuesta usando Gemini con contexto RAG"""
    ctx = retrieve(query, top_k=top_k)
    prompt = f"""
    Eres la memoria operativa de Clonnect.
    Usa SOLO la información de los fragmentos recuperados.
    ...
    """
    resp = gen_model.generate_content(prompt)
```

### 2.3 core/ingest.py - Ingestión de Archivos

| Campo | Valor |
|-------|-------|
| **Propósito** | Procesar y subir archivos (PDF, audio, texto) |
| **Líneas** | 157 |
| **Mapeo a módulo** | #2 Content Indexer, #6 Transcriber |
| **Estado** | Funcional |
| **¿Fusionado en CLONNECT?** | No |
| **Calidad** | ⭐⭐⭐⭐ |

**Funciones principales:**

```python
def extract_pdf_text(local_path: str) -> str:
    """Extrae texto de PDF con pdfplumber o PyPDF2"""

def transcribe_audio_gcs(gcs_uri: str) -> str:
    """Transcribe audio desde GCS usando Speech-to-Text"""
    client = speech.SpeechClient()
    audio = speech.RecognitionAudio(uri=gcs_uri)
    config = speech.RecognitionConfig(language_code="es-ES")

def upload_and_ingest(local_path: str, source: str | None = None):
    """Pipeline completo: sube → extrae → embeds → indexa"""
    # Soporta: .txt, .md, .json, .wav, .mp3, .m4a, .pdf
```

### 2.4 api/core_loader_api.py - Adapter Legacy

| Campo | Valor |
|-------|-------|
| **Propósito** | Wrapper para usar memory_core desde API |
| **Líneas** | 57 |
| **Estado** | Legacy |
| **¿Fusionado?** | No necesario |
| **Calidad** | ⭐⭐⭐ |

---

## 🔧 3. Dependencias y Tecnologías

### 3.1 Dependencias (api/requirements.txt)

| Paquete | Versión | Uso |
|---------|---------|-----|
| fastapi | 0.115.0 | Framework API |
| uvicorn[standard] | 0.30.6 | Servidor ASGI |
| orjson | 3.10.7 | JSON rápido |
| python-multipart | 0.0.9 | Upload de archivos |
| **google-cloud-storage** | 2.16.0 | GCS |
| **google-cloud-aiplatform** | 1.66.0 | Vertex AI embeddings |
| **google-cloud-speech** | 2.26.0 | Transcripción de audio |
| pypdf | 4.3.1 | Extracción de PDFs |
| numpy | 1.26.4 | Operaciones vectoriales |

### 3.2 Servicios Google Cloud

| Servicio | Uso |
|----------|-----|
| **Vertex AI** | Embeddings `text-embedding-004` + Gemini 2.5 Pro |
| **Cloud Speech-to-Text** | Transcripción de audio |
| **Cloud Storage** | Almacenamiento de índice y archivos |
| **Cloud Run** | Deploy de la API |
| **Secret Manager** | Tokens de autenticación |

### 3.3 Comparación de Stack

| Aspecto | clonnect-memory | Clonnect-creators |
|---------|-----------------|-------------------|
| **Embeddings** | Vertex AI (GCP) | sentence-transformers (local) |
| **Vector Store** | numpy en RAM | FAISS |
| **LLM** | Gemini 2.5 Pro | Groq/OpenAI/Anthropic |
| **Transcripción** | ✅ Google Speech | ❌ No tiene |
| **PDF Extraction** | ✅ pypdf | ❌ No tiene |
| **Storage** | GCS | PostgreSQL + archivos |

---

## 📊 4. Mapa de Cobertura de Módulos

| # | Módulo de Visión | ¿Existe? | Archivo(s) | Estado | ¿Fusionado? | Calidad | Notas |
|---|------------------|----------|------------|--------|-------------|---------|-------|
| 1 | Instagram Scraper | ❌ | - | - | - | - | No existe |
| 2 | Content Indexer | ✅ | `api/main.py`, `core/ingest.py` | Completo | **No** | ⭐⭐⭐⭐ | **VALIOSO** - Vertex AI embeddings |
| 3 | Tone Analyzer | ❌ | - | - | - | - | No existe |
| 4 | Content Citation | ❌ | - | - | - | - | No existe |
| 5 | Response Engine v2 | ⚠️ | `core/memory_core.py` | Parcial | Parcial | ⭐⭐⭐⭐ | Usa Gemini (diferente de main) |
| 6 | Transcriber | ✅ | `api/main.py:107-117`, `core/ingest.py:44-53` | Completo | **No** | ⭐⭐⭐⭐⭐ | **MUY VALIOSO** - Google STT |
| 7 | YouTube Connector | ❌ | - | - | - | - | No existe |
| 8 | Podcast Connector | ❌ | - | - | - | - | No existe |
| 9 | UI Base Conocimiento | ❌ | - | - | - | - | Es API, no UI |
| 10 | Import Wizard | ⚠️ | `api/main.py:309-349` | API básica | **No** | ⭐⭐⭐ | Upload endpoint, no wizard |
| 11 | Behavior Triggers | ❌ | - | - | - | - | No existe |
| 12 | Dynamic Offers | ❌ | - | - | - | - | No existe |
| 13 | Content Recommender | ❌ | - | - | - | - | No existe |
| 14 | Advanced Analytics | ❌ | - | - | - | - | Solo logs básicos |

### Resumen de Cobertura

| Categoría | Cubierto | Total | % |
|-----------|----------|-------|---|
| Magic Slice (1-5) | 2 | 5 | 40% |
| Alto Prioridad (6-8) | 1 | 3 | 33% |
| Medio Prioridad (9-14) | 0.5 | 6 | ~8% |
| **Total** | **~3.5** | **14** | **~25%** |

---

## 🔄 5. Módulos Descartados - Evaluación

Los módulos mencionados como "descartados" (TreeOfThoughts, Multimodal, Query Expansion, Cross-Encoder) **no existen en este repositorio**. Este repo contiene una implementación diferente centrada en:

| Módulo Encontrado | Descripción | ¿Reconsiderar? |
|-------------------|-------------|----------------|
| **Google Speech-to-Text** | Alternativa a Whisper | ✅ **SÍ** - Funciona bien, es cloud |
| **Vertex AI Embeddings** | Alternativa a sentence-transformers | ⚠️ Considerar - Depende de GCP |
| **PDF Extraction** | pypdf/pdfplumber | ✅ **SÍ** - No existe en main |
| **Upload Pipeline** | Procesa múltiples formatos | ✅ **SÍ** - Muy útil |

### Google Speech-to-Text vs Whisper

| Aspecto | Google STT (este repo) | Whisper |
|---------|------------------------|---------|
| **Latencia** | Más rápida (cloud) | Local pero más lenta |
| **Costo** | ~$0.006/15 seg | Gratis (local) |
| **Calidad ES** | Muy buena | Excelente |
| **Dependencias** | Solo API | Requiere GPU/modelo |

**Recomendación**: Mantener ambas opciones. Google STT para producción rápida, Whisper como fallback.

---

## 💎 6. Código Destacado para Reutilizar

### 6.1 Transcripción de Audio (NO EXISTE EN CLONNECT PRINCIPAL)

```python
def extract_text_from_audio(audio_bytes: bytes, language_code: str = "es-ES") -> str:
    """
    Transcribe audio usando Google Cloud Speech-to-Text.
    Soporta: mp3, wav, m4a, flac
    """
    from google.cloud import speech

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

**Valor**: ⭐⭐⭐⭐⭐ - **CRÍTICO** para módulo #6 Transcriber

### 6.2 Extracción de PDF (NO EXISTE EN CLONNECT PRINCIPAL)

```python
def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extrae texto de PDF usando pypdf"""
    from pypdf import PdfReader
    import io

    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n\n".join(pages)

# Versión alternativa con fallback
def extract_pdf_text(local_path: str) -> str:
    """Con fallback entre pdfplumber y PyPDF2"""
    if _PDF_BACKEND == "pdfplumber":
        with pdfplumber.open(local_path) as pdf:
            return "\n".join([p.extract_text() or "" for p in pdf.pages])
    elif _PDF_BACKEND == "pypdf2":
        import PyPDF2
        with open(local_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            return "\n".join([p.extract_text() or "" for p in reader.pages])
```

**Valor**: ⭐⭐⭐⭐⭐ - **CRÍTICO** para Content Indexer

### 6.3 Chunking con Overlap

```python
def split_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
    """Divide texto en chunks con overlap para mejor contexto"""
    text = text.strip()
    if not text:
        return []
    chunks = []
    start = 0
    n = len(text)
    while start < n:
        end = min(n, start + chunk_size)
        chunks.append(text[start:end])
        if end == n:
            break
        start = max(0, end - overlap)
    return chunks
```

**Valor**: ⭐⭐⭐⭐ - Mejora calidad de RAG

### 6.4 Upload Pipeline Completo

```python
@app.post("/ingest/upload")
async def ingest_upload(
    file: UploadFile = File(...),
    kind: Optional[str] = None,
    language_code: Optional[str] = "es-ES",
):
    """
    Pipeline unificado para ingestión de archivos:
    1. Detecta tipo (pdf, txt, json, audio)
    2. Extrae texto según tipo
    3. Divide en chunks
    4. Genera embeddings
    5. Guarda en índice
    """
    data = await file.read()
    detected = kind or detect_kind(filename, content_type)

    if detected == "pdf":
        text = extract_text_from_pdf(data)
    elif detected == "audio":
        text = extract_text_from_audio(data, language_code)
    elif detected in ("txt", "json"):
        text = data.decode("utf-8", errors="ignore")

    chunks = split_text(text)
    records = make_records(chunks, source_uri, detected)
    added = append_to_dataset_and_index(records)
```

**Valor**: ⭐⭐⭐⭐⭐ - Base perfecta para Import Wizard

---

## ⚠️ 7. Problemas Detectados

### 7.1 Código Duplicado con CLONNECT

| Funcionalidad | clonnect-memory | Clonnect-creators | ¿Cuál usar? |
|--------------|-----------------|-------------------|-------------|
| RAG/Embeddings | Vertex AI | sentence-transformers | Depende de infra |
| LLM calls | Gemini | Multi-provider | ✅ Clonnect-creators (más flexible) |
| API REST | FastAPI | FastAPI | Consolidar |
| Auth | Token header | Similar | Consolidar |

### 7.2 Problemas de Arquitectura

| Problema | Ubicación | Severidad | Descripción |
|----------|-----------|-----------|-------------|
| Variables globales | `core/memory_core.py` | 🟡 Media | Usa globals para estado |
| Sin FAISS | Todo | 🟡 Media | Búsqueda en numpy, no escala |
| GCP lock-in | Todo | 🟡 Media | Depende 100% de Google Cloud |
| Sin tests | Todo | 🟡 Media | 0 tests |

### 7.3 Configuración Hardcodeada

```python
# core/config.py - Valores hardcodeados
PROJECT_ID = "inlaid-tribute-476710-r2"  # ❌ Debería ser env var
LOCATION   = "us-central1"
BUCKET     = "clonnect-data"
```

---

## 📈 8. Resumen Ejecutivo

### 8.1 ¿Qué era Memory Engine?

El repositorio `clonnect-memory` es una **API de memoria RAG independiente** que:
- Usa **Vertex AI** para embeddings (alternativa a sentence-transformers)
- Usa **Google Cloud Speech-to-Text** para transcripción de audio
- Usa **Gemini** como LLM para respuestas
- Almacena todo en **Google Cloud Storage**
- Se despliega en **Cloud Run**

### 8.2 Estado de Fusión

| Componente | % Fusionado | En CLONNECT principal |
|------------|-------------|----------------------|
| RAG básico | 80% | Sí (con FAISS) |
| LLM integration | 50% | Sí (multi-provider, no Gemini) |
| **Transcripción** | **0%** | **NO** |
| **PDF extraction** | **0%** | **NO** |
| **Upload pipeline** | **0%** | **NO** |
| Cloud Run config | 100% | Sí (hay Dockerfile) |

### 8.3 Tesoros Escondidos

| Tesoro | Valor | Acción |
|--------|-------|--------|
| `extract_text_from_audio()` | ⭐⭐⭐⭐⭐ | **FUSIONAR YA** |
| `extract_text_from_pdf()` | ⭐⭐⭐⭐⭐ | **FUSIONAR YA** |
| `split_text()` con overlap | ⭐⭐⭐⭐ | Fusionar |
| Upload pipeline | ⭐⭐⭐⭐⭐ | Base para Import Wizard |
| Vertex AI embeddings | ⭐⭐⭐ | Opcional (GCP only) |

### 8.4 Recomendación Final

| Opción | Recomendación | Justificación |
|--------|---------------|---------------|
| Merge completo | ❌ No | Duplica RAG existente |
| **Merge selectivo** | ✅ **RECOMENDADO** | Extraer transcripción + PDF |
| Mantener separado | ⚠️ Considerar | Si se quiere stack GCP separado |
| Deprecar | ❌ No | Tiene código valioso |

### 8.5 Acciones Inmediatas (Priorizado)

1. **🔴 CRÍTICO - Fusionar transcripción de audio**
   - Copiar `extract_text_from_audio()` a Clonnect-creators
   - Añadir `google-cloud-speech` a requirements
   - Esto completa el módulo #6 Transcriber

2. **🔴 CRÍTICO - Fusionar extracción de PDF**
   - Copiar `extract_text_from_pdf()` a Clonnect-creators
   - Añadir `pypdf` a requirements
   - Mejora Content Indexer

3. **🟡 MEDIO - Implementar chunking con overlap**
   - Mejorar calidad de RAG

4. **🟡 MEDIO - Crear endpoint de upload unificado**
   - Base para Import Wizard (#10)

5. **🟢 BAJO - Evaluar Vertex AI embeddings**
   - Solo si se quiere stack GCP

---

## 📎 Anexo: Comparativa Técnica

```
┌─────────────────────────────────────────────────────────────────────┐
│                    STACK COMPARISON                                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  clonnect-memory:                     Clonnect-creators:            │
│  ┌─────────────────────┐              ┌─────────────────────┐       │
│  │ Vertex AI           │              │ sentence-transformers│       │
│  │ text-embedding-004  │              │ + FAISS              │       │
│  ├─────────────────────┤              ├─────────────────────┤       │
│  │ Google Speech-to-Text│  ← ÚNICO    │ ❌ No tiene          │       │
│  ├─────────────────────┤              ├─────────────────────┤       │
│  │ pypdf (PDF)         │  ← ÚNICO     │ ❌ No tiene          │       │
│  ├─────────────────────┤              ├─────────────────────┤       │
│  │ Gemini 2.5 Pro      │              │ Groq/OpenAI/Anthropic│       │
│  ├─────────────────────┤              ├─────────────────────┤       │
│  │ GCS                 │              │ PostgreSQL           │       │
│  └─────────────────────┘              └─────────────────────┘       │
│                                                                      │
│  FUSIONAR: Speech-to-Text + PDF extraction                          │
│  DESCARTAR: Embeddings (ya existe FAISS mejor)                      │
│  OPCIONAL: Gemini como provider adicional                           │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

*Auditoría generada automáticamente por Claude Code*
*Siguiente repo a auditar: (último de la lista)*
