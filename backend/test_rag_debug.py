#!/usr/bin/env python3
"""Debug RAG - Verificar por qué no encuentra contenido"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

print("=" * 70)
print("🔍 DEBUG RAG - Verificando búsqueda de contenido")
print("=" * 70)

# 1. Verificar conexión a DB
print("\n1. Verificando conexión a DB...")
from api.database import SessionLocal
from api.models import Creator, RAGDocument

if SessionLocal is None:
    print("❌ SessionLocal es None - no hay conexión a DB")
    exit(1)

print("✅ SessionLocal disponible")

# 2. Buscar creator
print("\n2. Buscando creator 'stefano_bonanno'...")
db = SessionLocal()
try:
    creator = db.query(Creator).filter(Creator.name == "stefano_bonanno").first()
    if creator:
        print(f"✅ Creator encontrado:")
        print(f"   ID: {creator.id}")
        print(f"   Name: {creator.name}")
        print(f"   Email: {creator.email}")
    else:
        print("❌ Creator NO encontrado")
        exit(1)

    # 3. Buscar RAG documents con ese creator_id
    print(f"\n3. Buscando RAG documents con creator_id = {creator.id}...")
    rag_docs = db.query(RAGDocument).filter(RAGDocument.creator_id == creator.id).limit(5).all()
    print(f"   Encontrados: {len(rag_docs)} (de los primeros 5)")

    if rag_docs:
        for doc in rag_docs[:3]:
            print(f"\n   Doc ID: {doc.doc_id}")
            print(f"   Content: {doc.content[:100]}...")
            print(f"   Source URL: {doc.source_url}")
    else:
        print("❌ NO hay RAG documents para este creator")

finally:
    db.close()

# 4. Probar citation_service directamente
print("\n4. Probando citation_service...")
from core.citation_service import get_content_index, get_citation_prompt_section

index = get_content_index("stefano_bonanno")
print(f"   Index stats: {index.stats}")
print(f"   Chunks cargados: {len(index.chunks)}")

# 5. Probar búsqueda
print("\n5. Probando búsqueda 'fitness estudiantes'...")
query = "grupo de estudiantes sports fitness"
results = index.search(query, max_results=5, min_relevance=0.1)
print(f"   Resultados: {len(results)}")

if results:
    for r in results[:3]:
        print(f"\n   - Relevance: {r['relevance_score']:.2f}")
        print(f"     Content: {r['content'][:100]}...")
else:
    print("   ❌ No se encontraron resultados")

# 6. Probar get_citation_prompt_section
print("\n6. Probando get_citation_prompt_section...")
citation_section = get_citation_prompt_section("stefano_bonanno", query, min_relevance=0.1)
if citation_section:
    print(f"   ✅ Citation section generada ({len(citation_section)} chars)")
    print(f"   Preview: {citation_section[:200]}...")
else:
    print("   ❌ Citation section VACÍA")

print("\n" + "=" * 70)
