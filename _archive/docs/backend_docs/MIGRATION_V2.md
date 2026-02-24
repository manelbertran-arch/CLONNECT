# Migración a Context Injection V2

## Resumen

Esta guía explica cómo activar, desactivar y verificar el nuevo sistema de Context Injection V2.

## Cambios Breaking

**Ninguno.** El feature flag `ENABLE_CONTEXT_INJECTION_V2` permite rollback instantáneo sin cambios de código.

## Cómo Activar/Desactivar

### Activar V2 (default)
```bash
# En Railway/producción
export ENABLE_CONTEXT_INJECTION_V2=true

# O simplemente no definir la variable (default es true)
```

### Rollback a V1
```bash
# En Railway/producción
export ENABLE_CONTEXT_INJECTION_V2=false
```

### Verificar Estado
```python
# En Python
from core.dm_agent import ENABLE_CONTEXT_INJECTION_V2
print(f"V2 enabled: {ENABLE_CONTEXT_INJECTION_V2}")
```

```bash
# En logs, buscar
grep "CONTEXT_INJECTION_V2" logs.txt
```

## Fast Paths Migrados

### Antes (V1): Fast paths retornan respuestas hardcoded
```python
if intent == Intent.ESCALATION:
    return DMResponse(
        response_text="Te paso con el creador...",  # Hardcoded
        ...
    )
```

### Después (V2): LLM decide con contexto
```python
if intent == Intent.ESCALATION and use_legacy_fast_paths:
    # Solo si V2 está desactivado
    return DMResponse(...)

# V2: El LLM ve el intent de escalación y decide
```

### Lista de Fast Paths Migrados

| # | Fast Path | Condición V1 | Comportamiento V2 |
|---|-----------|--------------|-------------------|
| 1 | USER_FRUSTRATED | Meta-message detected | Alerta en prompt, LLM responde con empatía |
| 2 | SARCASM_DETECTED | Patrón "ajá", "ya ya" | Alerta en prompt, LLM maneja |
| 3 | ESCALATION | intent == ESCALATION | Contexto de escalación, LLM decide |
| 4 | BOOKING | intent == BOOKING | Links de booking en prompt |
| 5 | INTEREST_STRONG | intent == INTEREST_STRONG | Links de pago en prompt |
| 6 | Direct Payment | Pregunta Bizum/PayPal | Métodos de pago en prompt |
| 7 | Price Question | "cuánto cuesta" | Precios en prompt, validación post |
| 8 | Direct Purchase | "quiero comprar" | Links en prompt |
| 9 | INTEREST_SOFT | intent == INTEREST_SOFT | Productos en prompt |
| 10 | LEAD_MAGNET | intent == LEAD_MAGNET | Lead magnets en prompt |
| 11 | THANKS | intent == THANKS post-booking | Contexto en historial |
| 12 | Anti-hallucination | INTENTS_REQUIRING_RAG | OutputValidator post-LLM |

## Tests

### Ejecutar todos los tests V2
```bash
# Tests unitarios
pytest tests/test_context_detector.py tests/test_prompt_builder.py tests/test_output_validator.py -v

# Tests de integración
pytest tests/test_integration_v2.py -v

# Todos juntos
pytest tests/test_context_detector.py tests/test_prompt_builder.py tests/test_output_validator.py tests/test_integration_v2.py -v
```

### Tests Críticos del Baseline
```bash
# Verificar caso Silvia específicamente
pytest tests/test_integration_v2.py::TestSilviaB2B -v
pytest tests/test_integration_v2.py::TestBaselineCritical -v
```

### Resultados Esperados
```
tests/test_context_detector.py: 69 passed
tests/test_prompt_builder.py: 46 passed
tests/test_output_validator.py: 46 passed
tests/test_integration_v2.py: 28 passed
Total: 189 passed
```

## Verificación Post-Deploy

### 1. Verificar Flag Activo
```bash
# En logs de Railway
grep "ENABLE_CONTEXT_INJECTION_V2" railway-logs.txt
```

### 2. Verificar Flujo V2
```bash
# Buscar logs del nuevo flujo
grep "CONTEXT_INJECTION_V2" railway-logs.txt | head -20
```

Deberías ver:
```
[CONTEXT_INJECTION_V2] Creator data loaded: X products
[CONTEXT_INJECTION_V2] User context loaded: name=..., messages=...
[CONTEXT_INJECTION_V2] Context detected: sentiment=..., frustration=...
[CONTEXT_INJECTION_V2] Built prompt with PromptBuilder: XXXX chars
[CONTEXT_INJECTION_V2] Response validated: ...
```

### 3. Verificar Caso Silvia
Envía un mensaje de prueba:
```
"Hola! Les escribe [Nombre] de [Empresa], ya habíamos trabajado antes"
```

**V2 correcto**: Respuesta profesional mencionando la colaboración
**V1 incorrecto**: "Entiendo que estás frustrado..."

### 4. Verificar Anti-Alucinación
Pregunta un precio y verifica:
- El precio en la respuesta coincide con el producto real
- No hay links inventados

## Rollback de Emergencia

Si hay problemas en producción:

### 1. Rollback Inmediato
```bash
# En Railway
railway variables set ENABLE_CONTEXT_INJECTION_V2=false
railway up
```

### 2. Verificar Rollback
```bash
# Los logs NO deben mostrar [CONTEXT_INJECTION_V2]
grep "CONTEXT_INJECTION_V2" railway-logs.txt
# Debe retornar vacío o mostrar que está desactivado
```

### 3. Reportar Issue
Si el rollback fue necesario, crear issue con:
- Mensaje que causó el problema
- Logs relevantes
- Comportamiento esperado vs actual

## Métricas a Monitorear

### Prometheus/Grafana
```promql
# % de mensajes procesados por LLM (debe subir de 45% a ~97%)
rate(dm_messages_to_llm_total[5m]) / rate(dm_messages_total[5m])

# Errores de validación
rate(output_validator_errors_total[5m])

# Tiempo de procesamiento
histogram_quantile(0.95, dm_processing_time_seconds_bucket)
```

### Logs
```bash
# Contar validaciones fallidas
grep "VALIDATION_ISSUE" logs.txt | wc -l

# Contar escalaciones por alucinación
grep "should_escalate.*True" logs.txt | wc -l
```

## FAQ

### ¿Qué pasa si el LLM falla?
El sistema tiene fallbacks:
1. Si `get_creator_data()` falla → usa fast paths legacy
2. Si `build_system_prompt()` falla → usa `_build_system_prompt()` legacy
3. Si `validate_response()` falla → usa respuesta sin validar

### ¿El caché afecta los cambios de productos?
- CreatorData se cachea 5 minutos
- Si actualizas productos, espera 5 min o reinicia el servicio

### ¿Puedo activar V2 solo para algunos creadores?
Actualmente no. El flag es global. Para A/B testing por creador, se necesitaría modificar el código.

### ¿Qué logs debo buscar para debugging?
```bash
# Flujo completo de un mensaje
grep "sender_id_aqui" logs.txt | grep -E "(CONTEXT_INJECTION|Intent:|Response:)"
```
