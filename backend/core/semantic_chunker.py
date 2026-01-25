"""
Semantic chunking that respects content boundaries.

Instead of fixed 500-char chunks, this creates chunks that:
1. Respect paragraph boundaries
2. Respect section boundaries (headers)
3. Keep sentences intact
4. Maintain context with smart overlap

Usage:
    chunker = SemanticChunker()
    chunks = chunker.chunk_text(text, source_url="https://example.com")
    for chunk in chunks:
        print(f"[{chunk.section_title}] {chunk.content[:50]}...")

Configuration (env vars):
    CHUNKING_MODE=semantic           # 'semantic' or 'fixed' (default: semantic)
    CHUNK_MAX_SIZE=800               # Max chars per chunk
    CHUNK_MIN_SIZE=100               # Min chars per chunk
    CHUNK_OVERLAP_SENTENCES=1        # Sentences to overlap for context
"""

import os
import re
import logging
from typing import List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================
CHUNKING_MODE = os.getenv("CHUNKING_MODE", "semantic")  # 'semantic' or 'fixed'
CHUNK_MAX_SIZE = int(os.getenv("CHUNK_MAX_SIZE", "800"))
CHUNK_MIN_SIZE = int(os.getenv("CHUNK_MIN_SIZE", "100"))
CHUNK_OVERLAP_SENTENCES = int(os.getenv("CHUNK_OVERLAP_SENTENCES", "1"))


# =============================================================================
# DATA CLASSES
# =============================================================================
@dataclass
class SemanticChunk:
    """Represents a semantically meaningful chunk of content."""
    content: str
    index: int
    source_url: str
    section_title: Optional[str] = None  # H1/H2/H3 that precedes this chunk
    chunk_type: str = "paragraph"  # 'paragraph', 'section', 'list', 'sentence'
    metadata: dict = field(default_factory=dict)

    @property
    def char_count(self) -> int:
        """Number of characters in content."""
        return len(self.content)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "content": self.content,
            "index": self.index,
            "source_url": self.source_url,
            "section_title": self.section_title,
            "chunk_type": self.chunk_type,
            "char_count": self.char_count,
            "metadata": self.metadata,
        }


# =============================================================================
# SEMANTIC CHUNKER
# =============================================================================
class SemanticChunker:
    """
    Chunker that respects semantic boundaries in text.

    Strategy:
    1. Identify section headers (# ## ### or HTML h1-h4)
    2. Split by paragraphs (double newlines)
    3. If paragraph > max_size, split by sentences
    4. Merge small adjacent chunks to meet min_size
    5. Add sentence overlap for context continuity
    """

    # Regex patterns
    HEADER_PATTERN = re.compile(r'^(#{1,4})\s+(.+)$', re.MULTILINE)
    SENTENCE_ENDINGS = re.compile(r'(?<=[.!?])\s+(?=[A-Z\u00c1\u00c9\u00cd\u00d3\u00da\u00d1])')
    PARAGRAPH_SPLIT = re.compile(r'\n\s*\n')

    def __init__(
        self,
        max_chunk_size: int = CHUNK_MAX_SIZE,
        min_chunk_size: int = CHUNK_MIN_SIZE,
        overlap_sentences: int = CHUNK_OVERLAP_SENTENCES,
    ):
        """
        Initialize SemanticChunker.

        Args:
            max_chunk_size: Maximum characters per chunk (default: 800)
            min_chunk_size: Minimum characters per chunk (default: 100)
            overlap_sentences: Number of sentences to overlap between chunks (default: 1)
        """
        self.max_chunk_size = max_chunk_size
        self.min_chunk_size = min_chunk_size
        self.overlap_sentences = overlap_sentences

    def chunk_text(self, text: str, source_url: str = "") -> List[SemanticChunk]:
        """
        Split text into semantic chunks.

        Strategy:
        1. Split by sections (## headers)
        2. Within sections, split by paragraphs
        3. If paragraph > max_size, split by sentences
        4. Merge small chunks, add overlap

        Args:
            text: Text content to chunk
            source_url: Source URL for tracking

        Returns:
            List of SemanticChunk objects
        """
        if not text or not text.strip():
            return []

        # Normalize whitespace
        text = text.strip()

        # Extract sections with headers
        sections = self._split_into_sections(text)

        chunks = []
        chunk_index = 0

        for section_title, section_content in sections:
            if not section_content.strip():
                continue

            # Split section into paragraphs
            paragraphs = self._split_into_paragraphs(section_content)

            for para in paragraphs:
                para = para.strip()
                if not para:
                    continue

                # If paragraph is small enough, use as-is
                if len(para) <= self.max_chunk_size:
                    chunks.append(SemanticChunk(
                        content=para,
                        index=chunk_index,
                        source_url=source_url,
                        section_title=section_title,
                        chunk_type="paragraph"
                    ))
                    chunk_index += 1
                else:
                    # Split long paragraph by sentences
                    sentence_chunks = self._split_long_paragraph(
                        para, section_title, source_url, chunk_index
                    )
                    chunks.extend(sentence_chunks)
                    chunk_index += len(sentence_chunks)

        # Merge small chunks
        chunks = self._merge_small_chunks(chunks)

        # Add overlap
        if self.overlap_sentences > 0:
            chunks = self._add_overlap(chunks)

        # Re-index after merging
        for i, chunk in enumerate(chunks):
            chunk.index = i

        logger.debug(f"Created {len(chunks)} semantic chunks from {len(text)} chars")
        return chunks

    def chunk_html(self, html: str, source_url: str = "") -> List[SemanticChunk]:
        """
        Chunk HTML content preserving structure.

        Uses BeautifulSoup to:
        1. Identify headers (h1-h4) as section boundaries
        2. Identify paragraphs (p) as natural chunks
        3. Identify lists (ul/ol) as atomic units

        Args:
            html: HTML content to chunk
            source_url: Source URL for tracking

        Returns:
            List of SemanticChunk objects
        """
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            logger.warning("BeautifulSoup not available, falling back to text chunking")
            return self.chunk_text(html, source_url)

        soup = BeautifulSoup(html, 'html.parser')

        # Remove script, style, nav, footer
        for tag in soup.find_all(['script', 'style', 'nav', 'footer', 'aside']):
            tag.decompose()

        chunks = []
        chunk_index = 0
        current_section = None

        # Process main content
        main = soup.find('main') or soup.find('article') or soup.find('body') or soup

        for element in main.find_all(['h1', 'h2', 'h3', 'h4', 'p', 'ul', 'ol', 'div']):
            # Update section title on headers
            if element.name in ['h1', 'h2', 'h3', 'h4']:
                current_section = element.get_text(strip=True)
                continue

            # Get text content
            if element.name in ['ul', 'ol']:
                # Keep lists together
                items = [li.get_text(strip=True) for li in element.find_all('li')]
                text = '. '.join(items)
                chunk_type = "list"
            else:
                text = element.get_text(strip=True)
                chunk_type = "paragraph"

            if not text or len(text) < 10:
                continue

            # Handle based on size
            if len(text) <= self.max_chunk_size:
                chunks.append(SemanticChunk(
                    content=text,
                    index=chunk_index,
                    source_url=source_url,
                    section_title=current_section,
                    chunk_type=chunk_type
                ))
                chunk_index += 1
            else:
                # Split long content
                sub_chunks = self._split_long_paragraph(
                    text, current_section, source_url, chunk_index
                )
                chunks.extend(sub_chunks)
                chunk_index += len(sub_chunks)

        # Merge small chunks and add overlap
        chunks = self._merge_small_chunks(chunks)
        if self.overlap_sentences > 0:
            chunks = self._add_overlap(chunks)

        # Re-index
        for i, chunk in enumerate(chunks):
            chunk.index = i

        logger.debug(f"Created {len(chunks)} semantic chunks from HTML")
        return chunks

    def _split_into_sections(self, text: str) -> List[tuple]:
        """
        Split text by markdown headers.

        Returns list of (section_title, section_content) tuples.
        """
        sections = []
        current_title = None
        current_content = []

        lines = text.split('\n')

        for line in lines:
            header_match = self.HEADER_PATTERN.match(line)
            if header_match:
                # Save previous section
                if current_content:
                    sections.append((current_title, '\n'.join(current_content)))
                    current_content = []

                current_title = header_match.group(2).strip()
            else:
                current_content.append(line)

        # Save last section
        if current_content:
            sections.append((current_title, '\n'.join(current_content)))

        # If no headers found, treat entire text as one section
        if not sections:
            sections = [(None, text)]

        return sections

    def _split_into_paragraphs(self, text: str) -> List[str]:
        """Split text by double newlines (paragraphs)."""
        paragraphs = self.PARAGRAPH_SPLIT.split(text)
        return [p.strip() for p in paragraphs if p.strip()]

    def _split_into_sentences(self, text: str) -> List[str]:
        """Split text into sentences."""
        # Use regex to split on sentence boundaries
        sentences = self.SENTENCE_ENDINGS.split(text)

        # Clean up and filter empty
        result = []
        for s in sentences:
            s = s.strip()
            if s:
                result.append(s)

        # If no splits found, return original text
        if not result:
            return [text] if text.strip() else []

        return result

    def _split_long_paragraph(
        self,
        text: str,
        section_title: Optional[str],
        source_url: str,
        start_index: int
    ) -> List[SemanticChunk]:
        """
        Split a long paragraph into sentence-based chunks.

        Groups sentences until max_chunk_size is reached.
        """
        sentences = self._split_into_sentences(text)

        if not sentences:
            return []

        chunks = []
        current_chunk = []
        current_size = 0
        chunk_index = start_index

        for sentence in sentences:
            sentence_size = len(sentence)

            # Would adding this sentence exceed max size?
            if current_size + sentence_size + 1 > self.max_chunk_size and current_chunk:
                # Save current chunk
                chunks.append(SemanticChunk(
                    content=' '.join(current_chunk),
                    index=chunk_index,
                    source_url=source_url,
                    section_title=section_title,
                    chunk_type="sentence"
                ))
                chunk_index += 1
                current_chunk = []
                current_size = 0

            current_chunk.append(sentence)
            current_size += sentence_size + 1  # +1 for space

        # Save remaining
        if current_chunk:
            chunks.append(SemanticChunk(
                content=' '.join(current_chunk),
                index=chunk_index,
                source_url=source_url,
                section_title=section_title,
                chunk_type="sentence"
            ))

        return chunks

    def _merge_small_chunks(self, chunks: List[SemanticChunk]) -> List[SemanticChunk]:
        """
        Merge adjacent small chunks that are under min_chunk_size.

        Only merges chunks with the same section_title.
        """
        if not chunks:
            return []

        merged = []
        current = chunks[0]

        for next_chunk in chunks[1:]:
            # Can we merge these?
            same_section = current.section_title == next_chunk.section_title
            combined_size = current.char_count + next_chunk.char_count + 1
            current_too_small = current.char_count < self.min_chunk_size
            combined_fits = combined_size <= self.max_chunk_size

            if same_section and current_too_small and combined_fits:
                # Merge
                current = SemanticChunk(
                    content=current.content + ' ' + next_chunk.content,
                    index=current.index,
                    source_url=current.source_url,
                    section_title=current.section_title,
                    chunk_type="merged"
                )
            else:
                # Save current and move to next
                merged.append(current)
                current = next_chunk

        # Don't forget the last one
        merged.append(current)

        return merged

    def _add_overlap(self, chunks: List[SemanticChunk]) -> List[SemanticChunk]:
        """
        Add sentence overlap to chunks for context continuity.

        Prepends the last N sentences from the previous chunk.
        """
        if len(chunks) <= 1 or self.overlap_sentences <= 0:
            return chunks

        result = [chunks[0]]  # First chunk has no previous context

        for i in range(1, len(chunks)):
            prev_chunk = chunks[i - 1]
            current_chunk = chunks[i]

            # Get last N sentences from previous chunk
            prev_sentences = self._split_into_sentences(prev_chunk.content)
            overlap_sentences = prev_sentences[-self.overlap_sentences:]

            if overlap_sentences and current_chunk.section_title == prev_chunk.section_title:
                # Prepend overlap (marked)
                overlap_text = ' '.join(overlap_sentences)

                # Only add if it doesn't make chunk too big
                if len(overlap_text) + len(current_chunk.content) + 1 <= self.max_chunk_size:
                    new_content = overlap_text + ' ' + current_chunk.content
                    current_chunk = SemanticChunk(
                        content=new_content,
                        index=current_chunk.index,
                        source_url=current_chunk.source_url,
                        section_title=current_chunk.section_title,
                        chunk_type=current_chunk.chunk_type,
                        metadata={"has_overlap": True}
                    )

            result.append(current_chunk)

        return result


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================
def get_semantic_chunker(
    max_size: int = CHUNK_MAX_SIZE,
    min_size: int = CHUNK_MIN_SIZE,
    overlap: int = CHUNK_OVERLAP_SENTENCES
) -> SemanticChunker:
    """Get a configured SemanticChunker instance."""
    return SemanticChunker(
        max_chunk_size=max_size,
        min_chunk_size=min_size,
        overlap_sentences=overlap
    )


def is_semantic_chunking_enabled() -> bool:
    """Check if semantic chunking is enabled via env var."""
    return CHUNKING_MODE.lower() == "semantic"


def chunk_content(
    text: str,
    source_url: str = "",
    mode: str = None
) -> List[dict]:
    """
    Chunk content using configured mode.

    Args:
        text: Text to chunk
        source_url: Source URL for tracking
        mode: Override chunking mode ('semantic' or 'fixed')

    Returns:
        List of chunk dictionaries with content and metadata
    """
    mode = mode or CHUNKING_MODE

    if mode.lower() == "semantic":
        chunker = SemanticChunker()
        chunks = chunker.chunk_text(text, source_url)
        return [chunk.to_dict() for chunk in chunks]
    else:
        # Fixed chunking fallback
        from ingestion.content_indexer import split_text
        text_chunks = split_text(text, chunk_size=500, overlap=50)
        return [
            {
                "content": chunk,
                "index": i,
                "source_url": source_url,
                "section_title": None,
                "chunk_type": "fixed",
                "char_count": len(chunk),
                "metadata": {}
            }
            for i, chunk in enumerate(text_chunks)
        ]


def get_chunking_stats() -> dict:
    """Get chunking configuration for debugging."""
    return {
        "mode": CHUNKING_MODE,
        "max_size": CHUNK_MAX_SIZE,
        "min_size": CHUNK_MIN_SIZE,
        "overlap_sentences": CHUNK_OVERLAP_SENTENCES,
        "semantic_enabled": is_semantic_chunking_enabled()
    }
