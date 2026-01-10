"""
Export FULL content from all scraped pages - NO TRUNCATION.
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def export_full_content(website_url: str, max_pages: int = 10):
    """Export complete content from all pages."""
    from ingestion.deterministic_scraper import DeterministicScraper

    scraper = DeterministicScraper(max_pages=max_pages)
    pages = await scraper.scrape_website(website_url)

    output_file = "/Users/manelbertranluque/Desktop/CLONNECT/backend/exports/stefano_full_content.txt"
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("EXPORTACIÓN COMPLETA DE CONTENIDO SCRAPEADO\n")
        f.write(f"Website: {website_url}\n")
        f.write(f"Total páginas: {len(pages)}\n")
        f.write(f"Total caracteres: {sum(len(p.main_content) for p in pages):,}\n")
        f.write("=" * 80 + "\n\n")

        for i, page in enumerate(pages, 1):
            f.write("\n")
            f.write("=" * 80 + "\n")
            f.write(f"PÁGINA {i}: {page.url}\n")
            f.write(f"Título: {page.title}\n")
            f.write(f"Caracteres: {len(page.main_content):,}\n")
            f.write("=" * 80 + "\n\n")

            # Write FULL content - NO TRUNCATION
            f.write(page.main_content)
            f.write("\n\n")
            f.write("-" * 80 + "\n")
            f.write(f"[FIN PÁGINA {i}]\n")
            f.write("-" * 80 + "\n")

    print(f"Contenido exportado a: {output_file}")
    print(f"Total páginas: {len(pages)}")
    print(f"Total caracteres: {sum(len(p.main_content) for p in pages):,}")

    return output_file


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "https://www.stefanobonanno.com"
    asyncio.run(export_full_content(url, 10))
