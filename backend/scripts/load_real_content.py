#!/usr/bin/env python3
"""
Load REAL scraped content from exports/stefano_full_content.txt to PostgreSQL.

This replaces fake/generated content with actual scraped website content.
"""

import re
import json
import httpx
import sys

# Configuration
API_URL = "https://www.clonnectapp.com"
CREATOR_ID = "stefano_auto"
CONTENT_FILE = "exports/stefano_full_content.txt"
CHUNK_SIZE = 500  # Characters per chunk


def parse_content_file(filepath: str) -> list:
    """
    Parse the exported content file into structured chunks.

    The file format is:
    ================================================================================
    PÁGINA X: {url}
    Título: {title}
    Caracteres: X
    ================================================================================
    {content}
    """
    chunks = []

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Split by page markers
    page_pattern = r'={80}\nPÁGINA \d+: (https?://[^\n]+)\nTítulo: ([^\n]+)\nCaracteres: \d+\n={80}\n'

    # Find all pages
    pages = re.split(page_pattern, content)

    # pages[0] is the header, then (url, title, content) triplets
    i = 1
    while i < len(pages) - 2:
        url = pages[i].strip()
        title = pages[i + 1].strip()
        page_content = pages[i + 2].strip()

        # Skip if content is too short
        if len(page_content) < 50:
            i += 3
            continue

        # Split into chunks with overlap
        text_chunks = split_into_chunks(page_content, CHUNK_SIZE, overlap=50)

        for j, chunk_text in enumerate(text_chunks):
            chunks.append({
                "content": chunk_text,
                "source_type": "web_page",
                "source_url": url,
                "title": f"{title} (parte {j+1}/{len(text_chunks)})" if len(text_chunks) > 1 else title
            })

        i += 3

    return chunks


def split_into_chunks(text: str, chunk_size: int, overlap: int = 50) -> list:
    """Split text into overlapping chunks, trying to break at sentence boundaries."""
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        # Try to find a good break point
        if end < len(text):
            # Look for sentence end
            for sep in ['. ', '? ', '! ', '\n\n', '\n']:
                last_sep = text.rfind(sep, start + chunk_size // 2, end)
                if last_sep > 0:
                    end = last_sep + len(sep)
                    break

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        start = end - overlap if end < len(text) else len(text)

    return chunks


def main():
    print(f"Loading real content from {CONTENT_FILE}")

    # Parse content file
    try:
        chunks = parse_content_file(CONTENT_FILE)
        print(f"Parsed {len(chunks)} chunks from website content")
    except FileNotFoundError:
        print(f"ERROR: File not found: {CONTENT_FILE}")
        sys.exit(1)

    if not chunks:
        print("ERROR: No chunks parsed from content file")
        sys.exit(1)

    # Step 1: Clear fake content
    print(f"\nStep 1: Clearing fake content for {CREATOR_ID}...")
    try:
        response = httpx.delete(f"{API_URL}/content/{CREATOR_ID}/clear", timeout=30)
        result = response.json()
        print(f"  Deleted {result.get('deleted_from_db', 0)} from DB, {result.get('deleted_from_rag', 0)} from RAG")
    except Exception as e:
        print(f"  Warning: Could not clear content: {e}")

    # Step 2: Load real content
    print(f"\nStep 2: Loading {len(chunks)} real chunks...")
    try:
        response = httpx.post(
            f"{API_URL}/content/bulk-load",
            json={
                "creator_id": CREATOR_ID,
                "chunks": chunks
            },
            timeout=120
        )
        result = response.json()
        print(f"  Loaded {result.get('chunks_loaded', 0)} chunks")
    except Exception as e:
        print(f"  ERROR: {e}")
        sys.exit(1)

    # Step 3: Verify
    print(f"\nStep 3: Verifying...")
    try:
        response = httpx.get(f"{API_URL}/content/stats?creator_id={CREATOR_ID}", timeout=30)
        result = response.json()
        print(f"  RAG in-memory: {result.get('rag_in_memory', 0)}")
        print(f"  DB persisted: {result.get('db_persisted', 0)}")
        print(f"  Synced: {result.get('synced', False)}")
    except Exception as e:
        print(f"  Warning: Could not verify: {e}")

    print("\nDone! Real website content loaded successfully.")


if __name__ == "__main__":
    main()
