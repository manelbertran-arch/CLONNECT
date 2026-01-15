#!/bin/bash
# checkpoint.sh - Crea un checkpoint (tag) del estado actual

set -e

if [ -z "$1" ]; then
    echo "Uso: ./scripts/checkpoint.sh <nombre-checkpoint>"
    echo "Ejemplo: ./scripts/checkpoint.sh sistema-verificado"
    exit 1
fi

CHECKPOINT_NAME="checkpoint-$1-$(date +%Y%m%d-%H%M)"

echo "Creando checkpoint: $CHECKPOINT_NAME"

# Verificar que estamos en un repo git
if [ ! -d ".git" ]; then
    echo "Error: No es un repositorio git"
    exit 1
fi

# Crear tag
git tag -a "$CHECKPOINT_NAME" -m "Checkpoint: $1"

echo "Checkpoint creado: $CHECKPOINT_NAME"
echo ""
echo "Para subir el tag al remoto:"
echo "  git push origin $CHECKPOINT_NAME"
echo ""
echo "Para listar checkpoints:"
echo "  git tag -l 'checkpoint-*'"
