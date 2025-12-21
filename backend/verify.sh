#!/bin/bash
echo "🔍 Verificando sintaxis Python..."
python3 -m py_compile api/main.py api/db_service.py api/database.py api/models.py
if [ $? -eq 0 ]; then
    echo "✅ Sintaxis OK"
else
    echo "❌ Error de sintaxis"
    exit 1
fi

echo "🔍 Verificando endpoints migrados..."
grep -c "if USE_DB:" api/main.py
echo "endpoints usando PostgreSQL"

echo "✅ Listo para push"
