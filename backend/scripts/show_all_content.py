"""
Script to show ALL raw content saved for a creator.
Shows products, RAG chunks, and testimonials with full literal text.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, or_
from sqlalchemy.orm import sessionmaker
from api.models import Creator, Product, RAGDocument

# Database connection
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/clonnect")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
db = Session()

def show_all_content(creator_name: str = "stefano_auto"):
    """Show all content for a creator."""

    # Find creator
    creator = db.query(Creator).filter(
        or_(
            Creator.name == creator_name,
            Creator.id == creator_name if len(creator_name) > 20 else False
        )
    ).first()

    if not creator:
        print(f"❌ Creator '{creator_name}' not found")
        return

    print(f"\n{'='*80}")
    print(f"CREATOR: {creator.name} (ID: {creator.id})")
    print(f"{'='*80}\n")

    # =========================================================================
    # 1. PRODUCTS
    # =========================================================================
    products = db.query(Product).filter(Product.creator_id == creator.id).all()

    print(f"\n{'#'*80}")
    print(f"# PRODUCTOS ({len(products)} total)")
    print(f"{'#'*80}\n")

    for i, p in enumerate(products, 1):
        print(f"\n{'='*60}")
        print(f"PRODUCTO #{i}: {p.name}")
        print(f"{'='*60}")
        print(f"ID: {p.id}")
        print(f"Price: {p.price} {p.currency if hasattr(p, 'currency') else 'EUR'}")
        print(f"Price Verified: {p.price_verified if hasattr(p, 'price_verified') else 'N/A'}")
        print(f"Confidence: {p.confidence if hasattr(p, 'confidence') else 'N/A'}")
        print(f"Source URL: {p.source_url if hasattr(p, 'source_url') else 'N/A'}")
        print(f"Is Active: {p.is_active}")
        print(f"\nDESCRIPTION:")
        print("-" * 40)
        print(p.description or "(empty)")
        print("-" * 40)

        # Check for source_html field
        if hasattr(p, 'source_html') and p.source_html:
            print(f"\nSOURCE HTML (first 2000 chars):")
            print("-" * 40)
            print(p.source_html[:2000] if len(p.source_html) > 2000 else p.source_html)
            print("-" * 40)

    # =========================================================================
    # 2. RAG DOCUMENTS
    # =========================================================================
    rag_docs = db.query(RAGDocument).filter(RAGDocument.creator_id == creator.id).limit(20).all()
    total_rag = db.query(RAGDocument).filter(RAGDocument.creator_id == creator.id).count()

    print(f"\n{'#'*80}")
    print(f"# RAG DOCUMENTS (showing 20 of {total_rag} total)")
    print(f"{'#'*80}\n")

    for i, doc in enumerate(rag_docs, 1):
        print(f"\n{'='*60}")
        print(f"RAG DOC #{i}: {doc.title or '(no title)'}")
        print(f"{'='*60}")
        print(f"Doc ID: {doc.doc_id}")
        print(f"Source URL: {doc.source_url}")
        print(f"Source Type: {doc.source_type}")
        print(f"Content Type: {doc.content_type}")
        print(f"Chunk Index: {doc.chunk_index if hasattr(doc, 'chunk_index') else 'N/A'}")
        print(f"\nFULL CONTENT:")
        print("-" * 40)
        print(doc.content)
        print("-" * 40)

    # =========================================================================
    # 3. TESTIMONIALS (if stored in products or separate)
    # =========================================================================
    # Check if testimonials are in RAG docs
    testimonials = db.query(RAGDocument).filter(
        RAGDocument.creator_id == creator.id,
        RAGDocument.content_type == 'testimonial'
    ).all()

    print(f"\n{'#'*80}")
    print(f"# TESTIMONIALS ({len(testimonials)} total)")
    print(f"{'#'*80}\n")

    if not testimonials:
        print("No testimonials found in RAG documents.")
        print("Checking products for testimonial-related content...")

        # Check for any content mentioning testimonials
        testimonial_rag = db.query(RAGDocument).filter(
            RAGDocument.creator_id == creator.id,
            RAGDocument.content.ilike('%testimoni%')
        ).all()

        if testimonial_rag:
            print(f"\nFound {len(testimonial_rag)} RAG docs mentioning testimonials:")
            for doc in testimonial_rag:
                print(f"\n  - {doc.title}: {doc.content[:200]}...")
    else:
        for i, t in enumerate(testimonials, 1):
            print(f"\n{'='*60}")
            print(f"TESTIMONIAL #{i}")
            print(f"{'='*60}")
            print(f"Source URL: {t.source_url}")
            print(f"\nFULL TEXT:")
            print("-" * 40)
            print(t.content)
            print("-" * 40)

    # =========================================================================
    # SUMMARY
    # =========================================================================
    print(f"\n{'#'*80}")
    print(f"# SUMMARY")
    print(f"{'#'*80}")
    print(f"Products: {len(products)}")
    print(f"RAG Documents: {total_rag}")
    print(f"Testimonials: {len(testimonials)}")

    # Products breakdown
    with_price = [p for p in products if p.price and p.price > 0]
    verified_price = [p for p in products if hasattr(p, 'price_verified') and p.price_verified]
    with_source = [p for p in products if hasattr(p, 'source_url') and p.source_url]

    print(f"\nProducts with price: {len(with_price)}")
    print(f"Products with verified price: {len(verified_price)}")
    print(f"Products with source_url: {len(with_source)}")


if __name__ == "__main__":
    creator = sys.argv[1] if len(sys.argv) > 1 else "stefano_auto"
    show_all_content(creator)
