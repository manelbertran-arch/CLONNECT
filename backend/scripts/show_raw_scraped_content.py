"""
Show RAW scraped content from each page - testimonials, etc.
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def show_raw_content(website_url: str, max_pages: int = 10):
    """Show all raw scraped content."""
    from ingestion.deterministic_scraper import DeterministicScraper

    print(f"\n{'='*80}")
    print("RAW SCRAPED CONTENT")
    print(f"URL: {website_url}")
    print(f"{'='*80}\n")

    scraper = DeterministicScraper(max_pages=max_pages)
    pages = await scraper.scrape_website(website_url)

    for i, page in enumerate(pages, 1):
        print(f"\n{'#'*80}")
        print(f"# PAGE #{i}: {page.url}")
        print(f"# Title: {page.title}")
        print(f"# Length: {len(page.main_content):,} chars")
        print(f"{'#'*80}\n")

        # Show first 3000 chars of content
        content = page.main_content
        print("RAW CONTENT (first 3000 chars):")
        print("-" * 60)
        print(content[:3000])
        if len(content) > 3000:
            print(f"\n... [{len(content) - 3000:,} more chars truncated]")
        print("-" * 60)

    # Specific search for testimonials
    print(f"\n{'#'*80}")
    print("# SEARCHING FOR TESTIMONIALS")
    print(f"{'#'*80}\n")

    testimonial_page = None
    for page in pages:
        if 'testimonio' in page.url.lower():
            testimonial_page = page
            break

    if testimonial_page:
        print(f"Found testimonials page: {testimonial_page.url}\n")
        print("FULL RAW CONTENT:")
        print("-" * 60)
        print(testimonial_page.main_content)
        print("-" * 60)
    else:
        print("No dedicated testimonials page found.")
        print("\nSearching for testimonial mentions in all pages...")
        for page in pages:
            if 'testimoni' in page.main_content.lower():
                print(f"\n  Found in: {page.url}")
                # Extract context around "testimoni"
                content = page.main_content
                idx = content.lower().find('testimoni')
                if idx > 0:
                    start = max(0, idx - 100)
                    end = min(len(content), idx + 500)
                    print(f"  Context: ...{content[start:end]}...")


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "https://www.stefanobonanno.com"
    max_pages = int(sys.argv[2]) if len(sys.argv) > 2 else 10

    asyncio.run(show_raw_content(url, max_pages))
