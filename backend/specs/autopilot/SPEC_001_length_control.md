# SPEC 001: Control de Longitud de Respuestas

## Objetivo
Reducir la longitud de las respuestas del bot para igualar el estilo de Stefan.

## Problema Actual
- Stefan: promedio 22 caracteres, mediana 18
- Bot V2: promedio 35-50 caracteres
- Error DEMASIADO_LARGO: 25.8%

## Criterios de Aceptación
- [ ] Longitud promedio del bot: 20-28 caracteres
- [ ] Error DEMASIADO_LARGO: <12%
- [ ] Respuestas cortas (<15 chars) aumentan de 20% a 40%
- [ ] No se pierde coherencia ni información crítica

## Implementación
1. Ajustar límites en prompt V2
2. Añadir regla de brevedad extrema para saludos/confirmaciones
3. Expandir pools de respuestas cortas
