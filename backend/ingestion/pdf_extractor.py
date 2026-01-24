"""
PDF Extractor - Extrae texto de PDFs y ebooks.

Soporta:
- PDFs locales y desde URL
- Extraccion de texto por pagina
- Metadatos del documento
- Chunking automatico para indexacion

Dependencias:
- pypdf (para extraccion de texto)
- httpx (para descargas)
"""

import asyncio
import hashlib
import logging
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PDFPage:
    """Contenido de una pagina de PDF."""

    page_number: int
    text: str
    char_count: int = 0

    def __post_init__(self):
        self.char_count = len(self.text)

    def to_dict(self) -> Dict:
        return {"page_number": self.page_number, "text": self.text, "char_count": self.char_count}


@dataclass
class PDFDocument:
    """Documento PDF extraido."""

    source: str  # path o URL
    title: str
    full_text: str
    pages: List[PDFPage] = field(default_factory=list)
    page_count: int = 0
    author: str = ""
    subject: str = ""
    keywords: List[str] = field(default_factory=list)
    creation_date: Optional[str] = None
    extracted_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def document_id(self) -> str:
        """Genera ID unico basado en source."""
        return hashlib.md5(self.source.encode()).hexdigest()[:12]

    @property
    def char_count(self) -> int:
        return len(self.full_text)

    @property
    def word_count(self) -> int:
        return len(self.full_text.split())

    def to_dict(self) -> Dict:
        return {
            "document_id": self.document_id,
            "source": self.source,
            "title": self.title,
            "full_text": self.full_text,
            "pages": [p.to_dict() for p in self.pages],
            "page_count": self.page_count,
            "author": self.author,
            "subject": self.subject,
            "keywords": self.keywords,
            "creation_date": self.creation_date,
            "extracted_at": self.extracted_at,
            "char_count": self.char_count,
            "word_count": self.word_count,
        }

    def get_text_by_pages(self, start: int = 1, end: Optional[int] = None) -> str:
        """
        Obtiene texto de un rango de paginas.

        Args:
            start: Pagina inicial (1-indexed)
            end: Pagina final (inclusive, None = hasta el final)

        Returns:
            Texto concatenado de las paginas
        """
        end = end or self.page_count
        selected_pages = [p for p in self.pages if start <= p.page_number <= end]
        return "\n\n".join(p.text for p in selected_pages)


class PDFExtractor:
    """
    Extractor de texto de documentos PDF.

    Uso:
        extractor = PDFExtractor()
        doc = await extractor.extract_file("documento.pdf")
        # Access result: doc.full_text
    """

    SUPPORTED_EXTENSIONS = {".pdf"}

    def __init__(self):
        """Inicializa el extractor."""
        pass

    async def extract_file(self, file_path: str) -> Optional[PDFDocument]:
        """
        Extrae texto de un archivo PDF local.

        Args:
            file_path: Ruta al archivo PDF

        Returns:
            PDFDocument o None si falla
        """
        path = Path(file_path)

        if not path.exists():
            logger.error(f"File not found: {file_path}")
            return None

        if path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
            logger.error(f"Unsupported format: {path.suffix}")
            return None

        try:
            return await self._extract_with_pypdf(str(path))
        except ImportError:
            logger.error("pypdf not installed. Install with: pip install pypdf")
            raise
        except Exception as e:
            logger.error(f"Error extracting PDF {file_path}: {e}")
            return None

    async def extract_url(self, url: str) -> Optional[PDFDocument]:
        """
        Descarga y extrae texto de un PDF desde URL.

        Args:
            url: URL del archivo PDF

        Returns:
            PDFDocument o None si falla
        """
        try:
            import httpx
        except ImportError:
            raise ImportError("httpx required. Install with: pip install httpx")

        with tempfile.TemporaryDirectory() as tmp_dir:
            try:
                pdf_path = Path(tmp_dir) / "document.pdf"

                logger.info(f"Downloading PDF from {url}")

                async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
                    response = await client.get(url)
                    response.raise_for_status()

                    with open(pdf_path, "wb") as f:
                        f.write(response.content)

                logger.info(f"Downloaded {pdf_path.stat().st_size / (1024*1024):.1f}MB")

                # Extraer y actualizar source a la URL original
                doc = await self._extract_with_pypdf(str(pdf_path))
                if doc:
                    doc.source = url

                return doc

            except Exception as e:
                logger.error(f"Error extracting PDF from URL {url}: {e}")
                return None

    async def _extract_with_pypdf(self, file_path: str) -> Optional[PDFDocument]:
        """Extrae usando pypdf."""
        try:
            from pypdf import PdfReader
        except ImportError:
            raise ImportError("pypdf required. Install with: pip install pypdf")

        # pypdf es sincrono, ejecutar en thread pool
        loop = asyncio.get_event_loop()

        def do_extract():
            reader = PdfReader(file_path)

            # Extraer metadatos
            metadata = reader.metadata or {}
            title = self._clean_metadata(metadata.get("/Title", "")) or Path(file_path).stem
            author = self._clean_metadata(metadata.get("/Author", ""))
            subject = self._clean_metadata(metadata.get("/Subject", ""))
            keywords_str = self._clean_metadata(metadata.get("/Keywords", ""))
            keywords = (
                [k.strip() for k in keywords_str.split(",") if k.strip()] if keywords_str else []
            )

            # Fecha de creacion
            creation_date = None
            if metadata.get("/CreationDate"):
                creation_date = self._parse_pdf_date(metadata["/CreationDate"])

            # Extraer texto por pagina
            pages = []
            full_text_parts = []

            for i, page in enumerate(reader.pages, start=1):
                try:
                    text = page.extract_text() or ""
                    text = self._clean_text(text)

                    if text:  # Solo agregar paginas con contenido
                        pages.append(PDFPage(page_number=i, text=text))
                        full_text_parts.append(text)
                except Exception as e:
                    logger.warning(f"Error extracting page {i}: {e}")
                    continue

            full_text = "\n\n".join(full_text_parts)

            return PDFDocument(
                source=file_path,
                title=title,
                full_text=full_text,
                pages=pages,
                page_count=len(reader.pages),
                author=author,
                subject=subject,
                keywords=keywords,
                creation_date=creation_date,
            )

        return await loop.run_in_executor(None, do_extract)

    def _clean_metadata(self, value) -> str:
        """Limpia valor de metadatos."""
        if value is None:
            return ""
        if isinstance(value, bytes):
            try:
                return value.decode("utf-8", errors="ignore")
            except Exception:
                return ""
        return str(value).strip()

    def _clean_text(self, text: str) -> str:
        """Limpia texto extraido."""
        if not text:
            return ""

        # Normalizar espacios en blanco
        import re

        # Reemplazar multiples espacios por uno
        text = re.sub(r"[ \t]+", " ", text)

        # Normalizar saltos de linea
        text = re.sub(r"\n{3,}", "\n\n", text)

        # Quitar espacios al inicio/final de lineas
        lines = [line.strip() for line in text.split("\n")]
        text = "\n".join(lines)

        return text.strip()

    def _parse_pdf_date(self, date_str) -> Optional[str]:
        """Parsea fecha en formato PDF (D:YYYYMMDDHHmmSS)."""
        try:
            if isinstance(date_str, bytes):
                date_str = date_str.decode("utf-8", errors="ignore")

            date_str = str(date_str)

            # Formato: D:YYYYMMDDHHmmSS o variantes
            if date_str.startswith("D:"):
                date_str = date_str[2:]

            # Extraer componentes (minimo YYYYMMDD)
            if len(date_str) >= 8:
                year = int(date_str[0:4])
                month = int(date_str[4:6])
                day = int(date_str[6:8])

                hour = int(date_str[8:10]) if len(date_str) >= 10 else 0
                minute = int(date_str[10:12]) if len(date_str) >= 12 else 0
                second = int(date_str[12:14]) if len(date_str) >= 14 else 0

                dt = datetime(year, month, day, hour, minute, second)
                return dt.isoformat()

        except Exception as e:
            logger.debug(f"Could not parse PDF date {date_str}: {e}")

        return None

    def chunk_document(
        self, document: PDFDocument, chunk_size: int = 500, overlap: int = 50
    ) -> List[Dict]:
        """
        Divide el documento en chunks para indexacion.

        Args:
            document: Documento PDF extraido
            chunk_size: Tamano aproximado de cada chunk (palabras)
            overlap: Palabras de solapamiento entre chunks

        Returns:
            Lista de chunks con metadata
        """
        chunks = []
        words = document.full_text.split()

        if not words:
            return chunks

        i = 0
        chunk_index = 0

        while i < len(words):
            # Obtener chunk
            end = min(i + chunk_size, len(words))
            chunk_words = words[i:end]
            chunk_text = " ".join(chunk_words)

            # Determinar pagina aproximada
            page_number = self._estimate_page(document, i, len(words))

            chunks.append(
                {
                    "chunk_id": f"{document.document_id}_chunk_{chunk_index}",
                    "document_id": document.document_id,
                    "source": document.source,
                    "title": document.title,
                    "content": chunk_text,
                    "chunk_index": chunk_index,
                    "page_number": page_number,
                    "word_count": len(chunk_words),
                }
            )

            chunk_index += 1
            i += chunk_size - overlap

        logger.info(f"Created {len(chunks)} chunks from {document.title}")
        return chunks

    def _estimate_page(self, document: PDFDocument, word_position: int, total_words: int) -> int:
        """Estima numero de pagina basado en posicion."""
        if not document.pages or total_words == 0:
            return 1

        # Proporcion simple
        ratio = word_position / total_words
        estimated_page = int(ratio * document.page_count) + 1

        return min(estimated_page, document.page_count)


# Singleton
_extractor: Optional[PDFExtractor] = None


def get_pdf_extractor() -> PDFExtractor:
    """Obtiene instancia singleton del extractor."""
    global _extractor
    if _extractor is None:
        _extractor = PDFExtractor()
    return _extractor
