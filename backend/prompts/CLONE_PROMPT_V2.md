# Clone System Prompt V2 - Universal

## Basado en análisis de 131 turnos reales

### Problemas detectados y solucionados:
| Problema | Frecuencia | Solución |
|----------|------------|----------|
| PREGUNTA_INNECESARIA | 35.1% | Política estricta de no preguntar |
| DEMASIADO_LARGO | 29.8% | Límites de longitud calculados |
| DEMASIADO_CORTO | 12.2% | Mínimo de longitud + contexto |
| RESPUESTA_GENERICA | 6.1% | Blacklist de frases prohibidas |
| EXCESO_EMOJIS | 4.6% | Límite basado en métricas |
| USA_PUNTO_FINAL | 3.8% | Política de puntuación |
| POOL_INADECUADO | 2.3% | Pools contextuales |

### Características del prompt:

1. **Universal**: Funciona con cualquier creador
2. **Métricas dinámicas**: Se inyectan del análisis del creador
3. **Ejemplos concretos**: Qué NO hacer
4. **Guías por tipo**: Respuestas según contexto

### Uso:

```python
from prompts.clone_system_prompt_v2 import get_stefan_prompt, extract_creator_metrics

# Para Stefan
prompt = get_stefan_prompt()

# Para otro creador
metrics = extract_creator_metrics(creator_id, messages)
prompt = build_clone_system_prompt(metrics)
```

### Métricas de Stefan (default):
- avg_length: 27.4 chars
- question_rate: 10%
- emoji_rate: 22%
- period_rate: 1.1%
- uses_dry_responses: True (15%)
