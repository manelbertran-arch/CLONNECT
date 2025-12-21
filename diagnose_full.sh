#!/bin/bash
echo "========== DIAGNÓSTICO COMPLETO =========="

echo ""
echo "=== 1. Verificar tabla messages existe ==="
grep -n "CREATE TABLE.*messages\|messages.*CREATE" backend/api/services/db_service.py | head -5

echo ""
echo "=== 2. Verificar USE_POSTGRES y pg_pool ==="
grep -n "USE_POSTGRES\|pg_pool" backend/api/services/db_service.py | head -10

echo ""
echo "=== 3. Dashboard metrics - qué query usa ==="
cat backend/api/routers/dashboard.py | grep -A 20 "total_messages\|get_creator_stats" | head -30

echo ""
echo "=== 4. Verificar que dm_agent tiene el código nuevo ==="
grep -n "SAVE TO POSTGRESQL" backend/core/dm_agent.py

echo ""
echo "=== 5. Verificar import path en dm_agent ==="
grep -n "from api.services.db_service" backend/core/dm_agent.py

echo ""
echo "=== 6. Railway logs (si hay error) ==="
curl -s https://web-production-9f69.up.railway.app/health/ready

echo ""
echo "=== 7. Test endpoint dashboard ==="
curl -s https://web-production-9f69.up.railway.app/dashboard/manel/overview | python3 -m json.tool 2>/dev/null | head -20

echo ""
echo "=== 8. Verificar si hay tabla messages en DB schema ==="
grep -n "messages" backend/api/services/db_service.py | head -10

echo ""
echo "========== FIN DIAGNÓSTICO =========="
