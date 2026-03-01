# CLONNECT — MASSIVE TEST REPORT v2

**Entorno:** Produccion (www.clonnectapp.com)

## RESUMEN

| Metrica | Valor |
|---------|-------|
| Tests ejecutados | 109 |
| PASS | 106 |
| FAIL | 2 |
| WARN | 1 |
| Pass rate | 97% |

## RESULTADOS DETALLADOS

| # | Test | Status | HTTP | Expected | Tiempo |
|---|------|--------|------|----------|--------|
| 1 | Health check | PASS | 200 | 200 | 0.76s |
| 2 | Health live | PASS | 200 | 200 | 0.98s |
| 3 | Health ready | PASS | 200 | 200 | 0.30s |
| 4 | Docs OpenAPI | PASS | 200 | 200 | 0.34s |
| 5 | OpenAPI JSON | PASS | 200 | 200 | 0.75s |
| 6 | Frontend loads | PASS | 200 | 200 | 1.46s |
| 7 | Login page | PASS | 200 | 200 | 0.55s |
| 8 | Dashboard page | PASS | 200 | 200 | 0.50s |
| 9 | Admin sin key → 401 | PASS | 401 | 401 | 0.43s |
| 10 | Admin con key → 200 | PASS | 200 | 200 | 1.19s |
| 11 | Metrics endpoint | PASS | 200 | 200 | 0.41s |
| 12 | Creator exists | PASS | 200 | 200 | 1.14s |
| 13 | Leads exist | PASS | 200 | 200 | 1.92s |
| 14 | Products exist | PASS | 200 | 200 | 0.91s |
| 15 | Messages exist | PASS | 200 | 200 | 4.36s |
| 16 | Knowledge exists | PASS | 200 | 200 | 1.71s |
| 17 | Tone exists | PASS | 200 | 200 | 0.39s |
| 18 | Analytics data | PASS | 200 | 200 | 0.30s |
| 19 | Health cache | PASS | 200 | 200 | 0.32s |
| 20 | DM hola | PASS | 200 | 200 | 4.56s |
| 21 | DM compra | PASS | 200 | 200 | 11.95s |
| 22 | DM emoji | PASS | 200 | 200 | 3.85s |
| 23 | DM largo | PASS | 200 | 200 | 11.21s |
| 24 | Copilot pending | FAIL | 500 | 200 | 1.43s |
| 25 | Copilot status | PASS | 200 | 200 | 2.12s |
| 26 | Copilot suggest (nuevo endpoint) | PASS | 404 | [404, 422] | 1.07s |
| 27 | Content search (GET) | PASS | 200 | 200 | 1.64s |
| 28 | Citations search (POST) | PASS | 200 | 200 | 0.44s |
| 29 | Clone score | PASS | 200 | 200 | 1.31s |
| 30 | DM metrics | PASS | 200 | 200 | 0.88s |
| 31 | DM leads list | PASS | 200 | 200 | 2.34s |
| 32 | Content stats | PASS | 200 | 200 | 1.21s |
| 33 | Admin GET /admin/stats | PASS | 200 | 200 | 0.93s |
| 34 | Admin GET /admin/conversations | PASS | 200 | 200 | 1.22s |
| 35 | Admin GET /admin/pending-messages | PASS | 200 | 200 | 1.07s |
| 36 | Admin GET /admin/alerts | PASS | 200 | 200 | 0.43s |
| 37 | Admin GET /admin/feature-flags | PASS | 200 | 200 | 0.35s |
| 38 | Admin GET /admin/demo-status | PASS | 200 | 200 | 1.86s |
| 39 | Admin GET /admin/creators | PASS | 200 | 200 | 1.68s |
| 40 | Admin GET /admin/sync-status/stefano_bonanno | PASS | 200 | 200 | 1.19s |
| 41 | Admin GET /admin/oauth/status/stefano_bonanno | PASS | 200 | 200 | 0.88s |
| 42 | Admin GET /admin/backups | PASS | 200 | 200 | 0.35s |
| 43 | Admin GET /admin/ingestion/status/stefano_bonanno | PASS | 200 | 200 | 2.06s |
| 44 | Admin GET /admin/lead-categories | PASS | 200 | 200 | 0.42s |
| 45 | Admin GET /admin/ghost-stats/stefano_bonanno | PASS | 200 | 200 | 1.97s |
| 46 | Admin GET /admin/ghost-config | PASS | 200 | 200 | 0.35s |
| 47 | Admin GET /admin/rate-limiter-stats | PASS | 200 | 200 | 0.30s |
| 48 | Creator GET /creator/config/stefano_bonanno | PASS | 200 | 200 | 1.41s |
| 49 | Creator GET /creator/list | FAIL | 0 | 200 | 15.00s |
| 50 | Creator GET /dashboard/stefano_bonanno/overview | PASS | 200 | 200 | 9.64s |
| 51 | Creator GET /creator/stefano_bonanno/products | PASS | 200 | 200 | 1.00s |
| 52 | Creator GET /creator/config/stefano_bonanno/knowledge | PASS | 200 | 200 | 1.58s |
| 53 | Creator GET /analytics/stefano_bonanno/sales | PASS | 200 | 200 | 0.38s |
| 54 | Creator GET /tone/stefano_bonanno | PASS | 200 | 200 | 0.33s |
| 55 | Creator GET /connections/stefano_bonanno | PASS | 200 | 200 | 1.29s |
| 56 | Creator GET /calendar/stefano_bonanno/links | PASS | 200 | 200 | 0.89s |
| 57 | Creator GET /insights/stefano_bonanno/today | PASS | 200 | 200 | 1.52s |
| 58 | Creator GET /intelligence/stefano_bonanno/dashboard | PASS | 200 | 200 | 3.59s |
| 59 | Creator GET /audience/stefano_bonanno/segments | PASS | 200 | 200 | 1.55s |
| 60 | Creator GET /audiencia/stefano_bonanno/topics | PASS | 200 | 200 | 0.88s |
| 61 | Creator GET /content/stats | PASS | 200 | 200 | 1.22s |
| 62 | Creator GET /citations/stefano_bonanno/stats | PASS | 200 | 200 | 0.39s |
| 63 | Creator GET /clone-score/stefano_bonanno | PASS | 200 | 200 | 1.08s |
| 64 | Creator GET /payments/stefano_bonanno/revenue | PASS | 200 | 200 | 0.42s |
| 65 | Creator GET /booking-links/stefano_bonanno | PASS | 200 | 200 | 1.66s |
| 66 | Creator GET /bot/stefano_bonanno/status | PASS | 200 | 200 | 1.19s |
| 67 | Creator GET /preview/status | PASS | 200 | 200 | 0.33s |
| 68 | Creator GET /leads/stefano_bonanno/unified | PASS | 200 | 200 | 2.71s |
| 69 | Leads GET /dm/leads/stefano_bonanno | PASS | 200 | 200 | 2.04s |
| 70 | Leads GET /dm/metrics/stefano_bonanno | PASS | 200 | 200 | 0.86s |
| 71 | Leads GET /admin/lead-categories | PASS | 200 | 200 | 0.59s |
| 72 | Nurturing GET /nurturing/stefano_bonanno/sequences | PASS | 200 | 200 | 0.39s |
| 73 | Nurturing GET /nurturing/stefano_bonanno/followups | PASS | 200 | 200 | 0.44s |
| 74 | Nurturing GET /nurturing/scheduler/status | PASS | 200 | 200 | 0.31s |
| 75 | DM GET /dm/conversations/stefano_bonanno | PASS | 200 | 200 | 0.90s |
| 76 | DM GET /dm/metrics/stefano_bonanno | PASS | 200 | 200 | 1.56s |
| 77 | DM GET /dm/leads/stefano_bonanno | PASS | 200 | 200 | 0.65s |
| 78 | OAuth GET /oauth/debug | PASS | 200 | 200 | 0.37s |
| 79 | OAuth GET /oauth/status/stefano_bonanno | PASS | 200 | 200 | 0.78s |
| 80 | Knowledge GET /creator/config/stefano_bonanno/knowledge/faqs | PASS | 200 | 200 | 1.45s |
| 81 | Knowledge GET /autolearning/stefano_bonanno/rules | PASS | 200 | 200 | 1.22s |
| 82 | Knowledge GET /autolearning/stefano_bonanno/dashboard | PASS | 200 | 200 | 2.71s |
| 83 | Other GET /maintenance/echo-status/stefano_bonanno | PASS | 200 | 200 | 1.45s |
| 84 | Other GET /debug/status | PASS | 200 | 200 | 0.39s |
| 85 | Other GET /events/stefano_bonanno | PASS | 401 | [200, 401] | 0.37s |
| 86 | Flow: DM pipeline completo | PASS | 200 | 200 | 11.50s |
| 87 | Flow: Webhook Instagram vacio | PASS | 400 | 400 | 0.44s |
| 88 | Flow: Webhook Stripe vacio | PASS | 200 | None | 2.47s |
| 89 | Flow: Webhook WhatsApp vacio | PASS | 200 | None | 0.37s |
| 90 | XSS attempt | PASS | 200 | 200 | 11.80s |
| 91 | Creator inexistente | PASS | 200 | [200, 404] | 1.54s |
| 92 | Creator inexistente products | PASS | 200 | [200, 404] | 1.19s |
| 93 | Creator inexistente config | PASS | 200 | [200, 404] | 0.88s |
| 94 | Empty body POST dm | PASS | 422 | [400, 422] | 0.39s |
| 95 | Missing fields dm | PASS | 422 | [400, 422] | 0.38s |
| 96 | Invalid JSON dm | PASS | 422 | 422 | 0.46s |
| 97 | Webhook invalid payload | PASS | 400 | 400 | 0.51s |
| 98 | Admin nuclear POST sin auth → 401 | PASS | 401 | 401 | 0.41s |
| 99 | Unicode heavy | PASS | 200 | 200 | 9.41s |
| 100 | SQL injection attempt | PASS | 200 | [200, 404, 422] | 1.58s |
| 101 | Path traversal encoded | PASS | 400 | [400, 404] | 0.38s |
| 102 | Path traversal etc/passwd | PASS | 400 | [400, 404] | 0.29s |
| 103 | Path traversal wp-admin | PASS | 400 | [400, 404] | 0.40s |
| 104 | Health timing #1 | PASS | 200 | 200 | 0.38s |
| 105 | Health timing #2 | WARN | 200 | 200 | 1.25s [SLOW: 1.2s > 1.0s] |
| 106 | Health timing #3 | PASS | 200 | 200 | 0.33s |
| 107 | Health timing #4 | PASS | 200 | 200 | 0.40s |
| 108 | Health timing #5 | PASS | 200 | 200 | 0.41s |
| 109 | DM timing | PASS | 200 | 200 | 10.37s |

## FALLOS

- **Copilot pending**: HTTP 500 (expected 200) 
- **Creator GET /creator/list**: HTTP 0 (expected 200) 

## WARNINGS

- **Health timing #2**: HTTP 200 [SLOW: 1.2s > 1.0s]

## TOP 10 MAS LENTOS

- 15.00s - Creator GET /creator/list
- 11.95s - DM compra
- 11.80s - XSS attempt
- 11.50s - Flow: DM pipeline completo
- 11.21s - DM largo
- 10.37s - DM timing
- 9.64s - Creator GET /dashboard/stefano_bonanno/overview
- 9.41s - Unicode heavy
- 4.56s - DM hola
- 4.36s - Messages exist
