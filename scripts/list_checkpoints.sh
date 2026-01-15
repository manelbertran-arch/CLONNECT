#!/bin/bash
# Lista todos los checkpoints disponibles

echo "═══════════════════════════════════════════════════════════════"
echo "  CHECKPOINTS DISPONIBLES"
echo "═══════════════════════════════════════════════════════════════"
echo ""

git tag | grep checkpoint | while read tag; do
    date=$(git log -1 --format=%ai "$tag" 2>/dev/null | cut -d' ' -f1)
    echo "  📍 $tag ($date)"
done

echo ""
echo "  Para volver a uno: ./scripts/rollback.sh <nombre>"
echo ""
