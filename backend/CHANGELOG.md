# CHANGELOG - Clonnect Creators

## [1.3.0] - 2026-01-17
### Added
- Sistema inteligente de señales y predicción de ventas (`api/services/signals.py`)
  - 30+ señales de compra/interés/objeciones
  - Detección automática de productos mencionados
  - Análisis de comportamiento (tiempo respuesta, longitud msgs)
  - Predicción de probabilidad de venta con confianza
  - Sugerencias de siguiente paso personalizadas
- Endpoint GET `/dm/leads/{creator_id}/escalations` para alertas de escalación
- Tests completos para signals.py (27 tests)

### Improved
- Caching con TTL de 5 minutos para análisis de señales
- Error handling robusto con graceful degradation
- Safe attribute access para evitar crashes
- Pestaña Actividad en frontend con métricas visuales

### Verified
- Rate limiter ya integrado en dm_agent.py ✓
- Notificaciones de escalación ya funcionando ✓
- Metodología Clonnect aplicada (no N+1, caching, error handling)

## [1.2.0] - 2026-01-16
### Added
- CRM completo con actividades y tareas
- Sistema de notas, email, teléfono por lead
- Historial de actividades con eliminación
- Animación de completar tareas

### Fixed
- Fix guardado de datos CRM (email, phone, notes)
- Fix pestaña Actividad vacía
- Fix rol de mensajes (user/assistant)

## [1.1.0] - 2026-01-15
### Added
- Pipeline visual con drag & drop
- Lead scoring por etapa del funnel
- Fotos de perfil en cards de Pipeline
- Click en foto abre perfil de Instagram

### Improved
- Unificación de etiquetas en español
- Mejora de colores en tags de status

## [1.0.1] - 2025-12-03
### Fixed
- Tests actualizados - 82/82 tests pasando
- Corregido imports y decoradores async

## [1.0.0] - 2025-12-02
### Added
- 45 funcionalidades MVP completas
- Instagram, WhatsApp, Telegram
- 9 idiomas, memoria por seguidor
- Stripe, Hotmart, Calendly
- 70+ endpoints API
