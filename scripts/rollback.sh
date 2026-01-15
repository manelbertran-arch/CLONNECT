#!/bin/bash
# USO: ./scripts/rollback.sh checkpoint-nombre-timestamp
# Vuelve al estado de un checkpoint guardado

set -e

TAG_NAME=$1

if [ -z "$TAG_NAME" ]; then
    echo "❌ Error: Proporciona el nombre del checkpoint"
    echo ""
    echo "Checkpoints disponibles:"
    git tag | grep checkpoint | tail -10
    exit 1
fi

echo "═══════════════════════════════════════════════════════════════"
echo "  ⚠️  ROLLBACK A: $TAG_NAME"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "  Esto va a:"
echo "  1. Guardar tu código actual en rama 'backup-antes-rollback'"
echo "  2. Volver el código al checkpoint"
echo "  3. Restaurar la DB (si hay backup)"
echo ""
read -p "  ¿Continuar? (y/n) " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelado."
    exit 0
fi

# 1. Guardar trabajo actual
BACKUP_BRANCH="backup-antes-rollback-$(date +%Y%m%d_%H%M%S)"
echo "📝 Guardando trabajo actual en rama: $BACKUP_BRANCH"
git checkout -b "$BACKUP_BRANCH"
git add .
git commit -m "Backup antes de rollback a $TAG_NAME" --allow-empty
git checkout main

# 2. Volver al checkpoint
echo "⏪ Volviendo al checkpoint..."
git reset --hard "$TAG_NAME"

# 3. Restaurar DB si existe backup
BACKUP_DIR="backups/${TAG_NAME}"
if [ -f "${BACKUP_DIR}/database.sql" ] && [ ! -z "$DATABASE_URL" ]; then
    echo "💾 Restaurando DB..."
    read -p "  ¿Restaurar base de datos? (y/n) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        psql "$DATABASE_URL" < "${BACKUP_DIR}/database.sql"
        echo "  ✅ DB restaurada"
    fi
fi

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  ✅ ROLLBACK COMPLETADO"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "  Tu código nuevo está en: $BACKUP_BRANCH"
echo "  Para recuperar commits: git cherry-pick <commit>"
echo ""
