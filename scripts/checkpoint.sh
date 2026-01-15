#!/bin/bash
# USO: ./scripts/checkpoint.sh "nombre-descriptivo"
# Guarda estado actual de código + base de datos

set -e

CHECKPOINT_NAME=$1
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

if [ -z "$CHECKPOINT_NAME" ]; then
    echo "❌ Error: Proporciona un nombre para el checkpoint"
    echo "   Uso: ./scripts/checkpoint.sh \"dashboard-funciona\""
    exit 1
fi

TAG_NAME="checkpoint-${CHECKPOINT_NAME}-${TIMESTAMP}"
BACKUP_DIR="backups/${TAG_NAME}"

echo "═══════════════════════════════════════════════════════════════"
echo "  CREANDO CHECKPOINT: $TAG_NAME"
echo "═══════════════════════════════════════════════════════════════"

# 1. Crear directorio de backup
mkdir -p "$BACKUP_DIR"

# 2. Commit cambios pendientes
echo "📝 Guardando cambios en git..."
git add .
git commit -m "CHECKPOINT: ${CHECKPOINT_NAME}" --allow-empty

# 3. Crear tag
echo "🏷️  Creando tag: $TAG_NAME"
git tag -a "$TAG_NAME" -m "Checkpoint: ${CHECKPOINT_NAME} - $(date)"

# 4. Backup de base de datos (si DATABASE_URL está configurado)
if [ ! -z "$DATABASE_URL" ]; then
    echo "💾 Guardando snapshot de DB..."
    pg_dump "$DATABASE_URL" > "${BACKUP_DIR}/database.sql" 2>/dev/null || echo "⚠️  No se pudo hacer backup de DB"
fi

# 5. Guardar estado actual de docs/CURRENT_STATE.md
if [ -f "docs/CURRENT_STATE.md" ]; then
    cp docs/CURRENT_STATE.md "${BACKUP_DIR}/CURRENT_STATE.md"
fi

# 6. Guardar info del checkpoint
cat > "${BACKUP_DIR}/INFO.txt" << EOF
Checkpoint: $CHECKPOINT_NAME
Tag: $TAG_NAME
Fecha: $(date)
Commit: $(git rev-parse HEAD)
Branch: $(git branch --show-current)
EOF

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  ✅ CHECKPOINT CREADO: $TAG_NAME"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "  📁 Backup en: $BACKUP_DIR"
echo "  🏷️  Tag: $TAG_NAME"
echo ""
echo "  Para volver a este punto:"
echo "  ./scripts/rollback.sh $TAG_NAME"
echo ""
