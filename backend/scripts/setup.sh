#!/bin/bash

# Clonnect Creators - Setup Script

echo "🤖 Clonnect Creators - Setup"
echo "============================"

# Crear entorno virtual
if [ ! -d "venv" ]; then
    echo "📦 Creando entorno virtual..."
    python3 -m venv venv
fi

# Activar entorno
echo "🔄 Activando entorno virtual..."
source venv/bin/activate

# Instalar dependencias
echo "📥 Instalando dependencias..."
pip install -r requirements.txt

# Crear directorios de datos
echo "📁 Creando directorios..."
mkdir -p data/creators data/products data/followers

# Crear .env si no existe
if [ ! -f ".env" ]; then
    echo "📝 Creando .env desde ejemplo..."
    cp .env.example .env
    echo "⚠️  Recuerda editar .env con tus claves!"
fi

echo ""
echo "✅ Setup completado!"
echo ""
echo "Para ejecutar:"
echo "  1. Activa el entorno: source venv/bin/activate"
echo "  2. Configura .env con tus claves"
echo "  3. Ejecuta API: ./scripts/run.sh api"
echo "  4. Ejecuta Dashboard: ./scripts/run.sh dashboard"
