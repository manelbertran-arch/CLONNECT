"""
Run V2 Ingestion Preview - Shows ALL raw content that would be extracted.
No database required - just shows detection results.
"""

import asyncio
import sys
import os
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def run_preview(website_url: str, max_pages: int = 10):
    """Run V2 preview and show all raw content."""
    from ingestion.v2 import IngestionV2Pipeline

    print(f"\n{'='*80}")
    print(f"V2 INGESTION PREVIEW")
    print(f"URL: {website_url}")
    print(f"Max Pages: {max_pages}")
    print(f"{'='*80}\n")

    # Run without DB = preview mode
    pipeline = IngestionV2Pipeline(db_session=None, max_pages=max_pages)
    result = await pipeline.run(
        creator_id="preview",
        website_url=website_url,
        clean_before=False,
        re_verify=True
    )

    # =========================================================================
    # SCRAPED PAGES
    # =========================================================================
    print(f"\n{'#'*80}")
    print(f"# SCRAPED PAGES ({result.pages_scraped} total, {result.total_chars:,} chars)")
    print(f"{'#'*80}\n")

    for page in result.pages_details:
        print(f"  - {page['url']} ({page['chars']:,} chars)")
        print(f"    Title: {page['title']}")

    # =========================================================================
    # DETECTED PRODUCTS
    # =========================================================================
    print(f"\n{'#'*80}")
    print(f"# DETECTED PRODUCTS ({len(result.products)} total)")
    print(f"{'#'*80}\n")

    for i, product in enumerate(result.products, 1):
        print(f"\n{'='*60}")
        print(f"PRODUCT #{i}: {product['name']}")
        print(f"{'='*60}")
        print(f"Source URL: {product['source_url']}")
        print(f"Signals Matched: {product['signals_matched']}")
        print(f"Confidence: {product['confidence']:.2%}")
        print(f"Price: {product['price']} {product['currency']}")
        print(f"Price Source Text: {product['price_source_text']}")

        print(f"\nDESCRIPTION:")
        print("-" * 40)
        print(product['description'])
        print("-" * 40)

    # =========================================================================
    # SANITY CHECKS
    # =========================================================================
    print(f"\n{'#'*80}")
    print(f"# SANITY CHECKS")
    print(f"{'#'*80}\n")

    for check in result.sanity_checks:
        status = "✅" if check['passed'] else "❌"
        print(f"  {status} {check['name']}: {check['message']}")

    # =========================================================================
    # ERRORS
    # =========================================================================
    if result.errors:
        print(f"\n{'#'*80}")
        print(f"# ERRORS")
        print(f"{'#'*80}\n")
        for error in result.errors:
            print(f"  ❌ {error}")

    # =========================================================================
    # SUMMARY
    # =========================================================================
    print(f"\n{'#'*80}")
    print(f"# SUMMARY")
    print(f"{'#'*80}")
    print(f"Status: {result.status}")
    print(f"Success: {result.success}")
    print(f"Pages Scraped: {result.pages_scraped}")
    print(f"Products Detected: {result.products_detected}")
    print(f"Products Verified: {result.products_verified}")
    print(f"Duration: {result.duration_seconds:.2f}s")

    # Products with prices
    with_price = [p for p in result.products if p['price']]
    print(f"\nProducts with verified price: {len(with_price)}")
    for p in with_price:
        print(f"  - {p['name']}: €{p['price']} (from: {p['price_source_text'][:50]}...)")

    return result


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "https://www.stefanobonanno.com"
    max_pages = int(sys.argv[2]) if len(sys.argv) > 2 else 10

    asyncio.run(run_preview(url, max_pages))
