#!/usr/bin/env python3
"""
Script para limpiar productos falsos (testimonios) de la base de datos.

Uso:
    python scripts/cleanup_fake_products.py --creator stefano_auto --dry-run
    python scripts/cleanup_fake_products.py --creator stefano_auto --execute
"""

import os
import sys
import re
import argparse

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Patrones que indican que es un TESTIMONIO, no un producto
TESTIMONIAL_PATTERNS = [
    r'\bme ayud[óo]\b', r'\bgracias a\b', r'\brecomiendo\b',
    r'\bcambi[óo] mi vida\b', r'\btransform[óo]\b',
    r'\bincreíble experiencia\b', r'\bmejor decisión\b',
    r'\bno puedo agradecer\b', r'\bestoy muy content[oa]\b',
    r'\bsuperó mis expectativas\b', r'\b100% recomendable\b',
    r'\bsi estás dudando\b', r'\bno lo dudes\b',
    r'\bme siento\b.*\b(mejor|genial|increíble)\b',
    r'\bél me enseñó\b', r'\bella me enseñó\b',
    r'\baprendí\b.*\bcon (él|ella|stefano)\b',
    r'\b(cliente|alumno|participante)\s+de\b',
]

def is_testimonial(name: str, description: str) -> bool:
    """Detecta si parece un testimonio."""
    name_lower = (name or "").lower().strip()
    desc_lower = (description or "").lower()

    # Título entre comillas = testimonio
    if name_lower.startswith('"') and name_lower.endswith('"'):
        return True
    if name_lower.startswith("'") and name_lower.endswith("'"):
        return True
    if name_lower.startswith('"') or name_lower.startswith('"'):
        return True

    # Comillas en cualquier parte del título corto
    if len(name_lower) < 60 and ('"' in name_lower or '"' in name_lower or '"' in name_lower):
        return True

    # Patrones en descripción
    matches = sum(1 for p in TESTIMONIAL_PATTERNS if re.search(p, desc_lower, re.IGNORECASE))
    if matches >= 1:
        return True

    return False


def main():
    parser = argparse.ArgumentParser(description='Limpiar productos falsos (testimonios)')
    parser.add_argument('--creator', required=True, help='Creator ID (ej: stefano_auto)')
    parser.add_argument('--dry-run', action='store_true', help='Solo mostrar qué se eliminaría')
    parser.add_argument('--execute', action='store_true', help='Ejecutar eliminación real')
    args = parser.parse_args()

    if not args.dry_run and not args.execute:
        print("❌ Debes especificar --dry-run o --execute")
        sys.exit(1)

    # Intentar importar supabase
    try:
        from backend.api.services.db_service import get_supabase_client
        supabase = get_supabase_client()
    except Exception as e:
        print(f"❌ Error conectando a DB: {e}")
        print("\nAlternativa: Ejecuta este SQL manualmente en Supabase:")
        print(f"""
-- Ver productos actuales de {args.creator}
SELECT id, name, price, description
FROM products
WHERE creator_id = '{args.creator}';

-- Eliminar testimonios (productos sin precio y con nombre entre comillas)
DELETE FROM products
WHERE creator_id = '{args.creator}'
AND price IS NULL
AND (
    name LIKE '"%' OR
    name LIKE '"%' OR
    description ILIKE '%me ayud%' OR
    description ILIKE '%gracias a%' OR
    description ILIKE '%recomiendo%'
);
        """)
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  LIMPIEZA DE PRODUCTOS FALSOS - {args.creator}")
    print(f"{'='*60}\n")

    # Obtener productos actuales
    result = supabase.table('products').select('*').eq('creator_id', args.creator).execute()
    products = result.data or []

    print(f"Productos encontrados: {len(products)}\n")

    to_delete = []
    to_keep = []

    for p in products:
        name = p.get('name', '')
        desc = p.get('description', '')
        price = p.get('price')

        if is_testimonial(name, desc):
            to_delete.append(p)
            print(f"❌ ELIMINAR (testimonio): {name[:50]}...")
            if desc:
                print(f"   Desc: {desc[:80]}...")
        else:
            to_keep.append(p)
            price_str = f"€{price}" if price else "sin precio"
            print(f"✅ MANTENER: {name[:50]}... ({price_str})")

    print(f"\n{'='*60}")
    print(f"  RESUMEN")
    print(f"{'='*60}")
    print(f"  Mantener: {len(to_keep)}")
    print(f"  Eliminar: {len(to_delete)}")

    if args.execute and to_delete:
        print(f"\n⚠️  Eliminando {len(to_delete)} productos falsos...")
        for p in to_delete:
            supabase.table('products').delete().eq('id', p['id']).execute()
            print(f"   Eliminado: {p['name'][:40]}...")
        print(f"\n✅ Limpieza completada")
    elif args.dry_run:
        print(f"\n📋 Modo dry-run. Usa --execute para eliminar realmente.")


if __name__ == "__main__":
    main()
