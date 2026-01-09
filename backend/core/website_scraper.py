"""
Website Scraper - Extrae contenido de websites para indexar en RAG.

Usado durante el auto-onboarding para enriquecer el conocimiento del bot
con información del sitio web del creator.
"""

import re
import logging
from typing import Optional, List, Dict, Any
from urllib.parse import urljoin, urlparse
import httpx

logger = logging.getLogger(__name__)

# URLs to skip (navigation, social, etc.)
SKIP_PATTERNS = [
    r'/login', r'/signin', r'/signup', r'/register',
    r'/cart', r'/checkout', r'/account',
    r'/privacy', r'/terms', r'/legal',
    r'facebook\.com', r'twitter\.com', r'instagram\.com',
    r'youtube\.com', r'linkedin\.com', r'tiktok\.com',
    r'\.pdf$', r'\.zip$', r'\.exe$', r'\.dmg$'
]


def extract_url_from_text(text: str) -> Optional[str]:
    """
    Extrae la primera URL de un texto (bio de Instagram, etc.).

    Args:
        text: Texto que puede contener una URL

    Returns:
        URL encontrada o None
    """
    if not text:
        return None

    # Patrones comunes de URLs
    url_patterns = [
        r'https?://[^\s<>"\']+',
        r'www\.[^\s<>"\']+',
        r'[a-zA-Z0-9-]+\.(com|es|net|org|io|co|link|bio|me)[^\s<>"\']*'
    ]

    for pattern in url_patterns:
        match = re.search(pattern, text)
        if match:
            url = match.group()
            # Limpiar caracteres finales comunes
            url = url.rstrip('.,;:!?)')
            # Asegurar protocolo
            if not url.startswith('http'):
                url = 'https://' + url
            return url

    return None


async def scrape_website_content(
    url: str,
    max_pages: int = 5,
    timeout: float = 10.0
) -> List[Dict[str, Any]]:
    """
    Scrapea contenido de un website.

    Args:
        url: URL base del sitio
        max_pages: Maximo de paginas a scrapear
        timeout: Timeout por request

    Returns:
        Lista de dicts con {url, title, content}
    """
    results = []
    visited = set()
    to_visit = [url]

    # Extraer dominio base
    parsed = urlparse(url)
    base_domain = f"{parsed.scheme}://{parsed.netloc}"

    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; ClonnectBot/1.0; +https://clonnect.com)"
        }
    ) as client:
        while to_visit and len(results) < max_pages:
            current_url = to_visit.pop(0)

            if current_url in visited:
                continue

            # Skip certain URLs
            if any(re.search(p, current_url, re.I) for p in SKIP_PATTERNS):
                continue

            visited.add(current_url)

            try:
                response = await client.get(current_url)

                if response.status_code != 200:
                    continue

                content_type = response.headers.get('content-type', '')
                if 'text/html' not in content_type:
                    continue

                html = response.text

                # Extraer contenido
                page_content = extract_text_from_html(html)
                title = extract_title_from_html(html)

                if page_content and len(page_content) > 100:
                    results.append({
                        "url": current_url,
                        "title": title or current_url,
                        "content": page_content
                    })
                    logger.info(f"[WebScraper] Scraped {current_url}: {len(page_content)} chars")

                # Extraer links para seguir (solo del mismo dominio)
                if len(results) < max_pages:
                    links = extract_links_from_html(html, base_domain)
                    for link in links:
                        if link not in visited and link not in to_visit:
                            to_visit.append(link)

            except httpx.TimeoutException:
                logger.warning(f"[WebScraper] Timeout scraping {current_url}")
            except Exception as e:
                logger.warning(f"[WebScraper] Error scraping {current_url}: {e}")

    logger.info(f"[WebScraper] Total pages scraped: {len(results)}")
    return results


def extract_text_from_html(html: str) -> str:
    """Extrae texto limpio de HTML."""
    # Remover scripts, styles, nav, footer
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.I)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.I)
    html = re.sub(r'<nav[^>]*>.*?</nav>', '', html, flags=re.DOTALL | re.I)
    html = re.sub(r'<footer[^>]*>.*?</footer>', '', html, flags=re.DOTALL | re.I)
    html = re.sub(r'<header[^>]*>.*?</header>', '', html, flags=re.DOTALL | re.I)
    html = re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)

    # Remover todas las tags HTML
    text = re.sub(r'<[^>]+>', ' ', html)

    # Limpiar whitespace
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()

    # Decodificar entidades HTML comunes
    text = text.replace('&nbsp;', ' ')
    text = text.replace('&amp;', '&')
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    text = text.replace('&quot;', '"')
    text = text.replace('&#39;', "'")

    return text


def extract_title_from_html(html: str) -> Optional[str]:
    """Extrae el titulo de una pagina HTML."""
    # Buscar <title>
    match = re.search(r'<title[^>]*>([^<]+)</title>', html, re.I)
    if match:
        return match.group(1).strip()

    # Buscar <h1>
    match = re.search(r'<h1[^>]*>([^<]+)</h1>', html, re.I)
    if match:
        return match.group(1).strip()

    return None


def extract_links_from_html(html: str, base_domain: str) -> List[str]:
    """Extrae links del mismo dominio."""
    links = []

    # Buscar href
    for match in re.finditer(r'href=["\']([^"\']+)["\']', html, re.I):
        href = match.group(1)

        # Skip anchors and javascript
        if href.startswith('#') or href.startswith('javascript:'):
            continue

        # Convertir a URL absoluta
        if href.startswith('/'):
            href = base_domain + href
        elif not href.startswith('http'):
            continue

        # Solo incluir del mismo dominio
        if urlparse(href).netloc == urlparse(base_domain).netloc:
            # Limpiar query string y fragment
            href = href.split('?')[0].split('#')[0]
            if href and href not in links:
                links.append(href)

    return links[:20]  # Limitar para no explotar


async def scrape_and_index_website(
    creator_id: str,
    url: str,
    max_pages: int = 5
) -> Dict[str, Any]:
    """
    Scrapea un website y lo indexa en RAG para el creator.

    Args:
        creator_id: ID del creator
        url: URL del website
        max_pages: Maximo de paginas a scrapear

    Returns:
        Dict con estadisticas de la indexacion
    """
    from core.rag import get_hybrid_rag
    from ingestion.content_indexer import create_chunks_from_content

    stats = {
        "url": url,
        "pages_scraped": 0,
        "chunks_indexed": 0,
        "errors": []
    }

    try:
        # Scrapear website
        pages = await scrape_website_content(url, max_pages=max_pages)
        stats["pages_scraped"] = len(pages)

        if not pages:
            stats["errors"].append("No content found on website")
            return stats

        # Indexar en RAG
        rag = get_hybrid_rag()

        for page in pages:
            try:
                # Crear chunks del contenido
                chunks = create_chunks_from_content(
                    creator_id=creator_id,
                    source_type="website",
                    source_id=page["url"],
                    content=page["content"],
                    title=page["title"],
                    source_url=page["url"],
                    metadata={
                        "creator_id": creator_id,
                        "source": "website",
                        "page_title": page["title"]
                    },
                    chunk_size=500,
                    overlap=50
                )

                # Indexar cada chunk
                for chunk in chunks:
                    rag.add_document(
                        doc_id=chunk.id,
                        text=chunk.content,
                        metadata={
                            "creator_id": creator_id,
                            "source_type": "website",
                            "source_url": chunk.source_url,
                            "title": chunk.title
                        }
                    )
                    stats["chunks_indexed"] += 1

            except Exception as e:
                error_msg = f"Error indexing {page['url']}: {e}"
                logger.error(f"[WebScraper] {error_msg}")
                stats["errors"].append(error_msg)

        logger.info(f"[WebScraper] Indexed {stats['chunks_indexed']} chunks from {stats['pages_scraped']} pages for {creator_id}")

    except Exception as e:
        error_msg = f"Error scraping website: {e}"
        logger.error(f"[WebScraper] {error_msg}")
        stats["errors"].append(error_msg)

    return stats
