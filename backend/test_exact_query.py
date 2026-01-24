#!/usr/bin/env python3
"""Test con la query exacta del mensaje 2"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from core.citation_service import get_content_index, get_citation_prompt_section, clear_index_cache

# Query exacta del mensaje 2
query = "Les escribo en esta ocasión porque tenemos un grupo de estudiantes del área Sports and fitness que llegan de Irlanda en febrero, que quizás podrían interesarles"

print("=" * 70)
print("🔍 TEST QUERY EXACTA")
print("=" * 70)
print(f"\nQuery: {query}")

# Limpiar cache para forzar recarga
clear_index_cache("stefano_bonanno")
print("\n✓ Cache limpiado")

# Obtener index
index = get_content_index("stefano_bonanno")
print(f"✓ Index cargado: {len(index.chunks)} chunks")

# Probar búsqueda con diferentes min_relevance
for min_rel in [0.5, 0.4, 0.3, 0.25, 0.2, 0.1, 0.0]:
    results = index.search(query, max_results=3, min_relevance=min_rel)
    print(f"\n   min_relevance={min_rel}: {len(results)} resultados")
    if results and min_rel <= 0.25:
        for r in results[:2]:
            print(f"      - {r['relevance_score']:.2f}: {r['content'][:60]}...")

# Test get_citation_prompt_section
print("\n" + "-" * 70)
print("get_citation_prompt_section con min_relevance=0.25:")
citation = get_citation_prompt_section("stefano_bonanno", query, min_relevance=0.25)
if citation:
    print(f"✅ Encontrado ({len(citation)} chars)")
else:
    print("❌ VACÍO - esto causa el escalado")

# Verificar keywords extraídos
print("\n" + "-" * 70)
print("Keywords extraídos de la query:")
from ingestion import extract_topics_from_query
keywords = extract_topics_from_query(query)
print(f"   {keywords}")

print("\n" + "=" * 70)
