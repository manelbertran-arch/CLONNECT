"""
Content Indexer - Indexa contenido del creador en RAG con chunking inteligente.
Fase 1 - Magic Slice
"""

from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime
import hashlib


@dataclass
class ContentChunk:
    """Representa un fragmento de contenido indexado."""
    id: str
    creator_id: str
    source_type: str  # 'instagram_post', 'instagram_reel', 'youtube', 'podcast', 'pdf'
    source_id: str  # ID original del contenido (post_id, video_id, etc.)
    source_url: Optional[str]
    title: Optional[str]
    content: str
    chunk_index: int
    total_chunks: int
    metadata: Dict
    created_at: datetime


def split_text(
    text: str,
    chunk_size: int = 500,
    overlap: int = 50
) -> List[str]:
    """
    Divide texto en chunks con overlap para mejor contexto en RAG.

    Migrado de clonnect-memory/api/main.py:83-96
    Mejorado con:
    - Respeta limites de oraciones cuando es posible
    - Overlap configurable para mantener contexto

    Args:
        text: Texto a dividir
        chunk_size: Tamano objetivo de cada chunk (caracteres)
        overlap: Caracteres de solapamiento entre chunks

    Returns:
        Lista de chunks de texto
    """
    if not text or len(text) <= chunk_size:
        return [text] if text else []

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        # Si no es el ultimo chunk, intentar cortar en un punto natural
        if end < len(text):
            # Buscar el ultimo punto, signo de interrogacion o exclamacion
            last_sentence_end = max(
                text.rfind('. ', start, end),
                text.rfind('? ', start, end),
                text.rfind('! ', start, end),
                text.rfind('\n', start, end)
            )

            # Si encontramos un buen punto de corte, usarlo
            if last_sentence_end > start + chunk_size // 2:
                end = last_sentence_end + 1

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        # Siguiente chunk empieza con overlap
        start = end - overlap if end < len(text) else end

    return chunks


def generate_chunk_id(creator_id: str, source_type: str, source_id: str, chunk_index: int) -> str:
    """Genera un ID unico para un chunk."""
    raw = f"{creator_id}:{source_type}:{source_id}:{chunk_index}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def create_chunks_from_content(
    creator_id: str,
    source_type: str,
    source_id: str,
    content: str,
    title: Optional[str] = None,
    source_url: Optional[str] = None,
    metadata: Optional[Dict] = None,
    chunk_size: int = 500,
    overlap: int = 50
) -> List[ContentChunk]:
    """
    Crea chunks indexables desde contenido raw.

    Args:
        creator_id: ID del creador
        source_type: Tipo de fuente ('instagram_post', 'youtube', etc.)
        source_id: ID original del contenido
        content: Texto del contenido
        title: Titulo opcional
        source_url: URL de origen opcional
        metadata: Metadatos adicionales (fecha publicacion, likes, etc.)
        chunk_size: Tamano de chunks
        overlap: Solapamiento entre chunks

    Returns:
        Lista de ContentChunk listos para indexar
    """
    text_chunks = split_text(content, chunk_size, overlap)

    chunks = []
    for i, text in enumerate(text_chunks):
        chunk = ContentChunk(
            id=generate_chunk_id(creator_id, source_type, source_id, i),
            creator_id=creator_id,
            source_type=source_type,
            source_id=source_id,
            source_url=source_url,
            title=title,
            content=text,
            chunk_index=i,
            total_chunks=len(text_chunks),
            metadata=metadata or {},
            created_at=datetime.utcnow()
        )
        chunks.append(chunk)

    return chunks


# TODO Fase 1: Anadir funciones para:
# - index_chunks_to_faiss(): Indexar chunks en FAISS
# - search_content(): Buscar contenido relevante
# - get_citation_context(): Obtener contexto para citas
