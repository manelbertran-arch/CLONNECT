# CAPA 1 — Verificación Base de Datos

**Fecha**: 2026-02-26 06:42 UTC

## Resultado: 27/27 PASS (100%)

| Test | Estado | Detalle |
|------|--------|--------|
| Tablas críticas presentes | ✅ | 59 tablas encontradas |
| Tablas extra en DB (no en modelos) | ⚠️ | {'creator_calibrations', 'content_embeddings', 'leads_backup_20260204'} |
| Migraciones al día | ✅ | DB=['035'], heads=['033', '035'] ✓ |
| FK: leads sin creator | ✅ | 0 huérfanos ✓ |
| FK: messages sin lead | ✅ | 0 huérfanos ✓ |
| FK: products sin creator | ✅ | 0 huérfanos ✓ |
| FK: learning_rules sin creator | ✅ | 0 huérfanos ✓ |
| FK: nurturing_followups sin cre | ✅ | 0 huérfanos ✓ |
| FK: tone_profiles sin creator | ✅ | 0 huérfanos ✓ |
| Index creators.name | ✅ | índice presente |
| Index leads.creator_id | ✅ | índice presente |
| Index leads.platform_user_id | ✅ | índice presente |
| Index messages.lead_id | ✅ | índice presente |
| Index messages.platform_message_id | ✅ | índice presente |
| pgvector instalado | ✅ | versión 0.8.0 |
| rag_documents (docs totales) | ✅ | 1029 registros |
| conversation_embeddings (embeddings) | ✅ | 10814 registros |
| Vector indexes (hnsw/ivfflat) | ✅ | 2 índices vectoriales |
| Creator stefano_bonanno existe | ✅ | UUID=5e5c2364... bot_active=True |
| stefano.leads | ✅ | 934 registros |
| stefano.messages | ✅ | 73851 registros |
| stefano.products | ✅ | 2 registros |
| stefano.knowledge_base | ✅ | 22 registros |
| stefano.rag_documents | ✅ | 1029 registros |
| stefano.tone_profiles | ✅ | 0 registros |
| stefano.nurturing_sequences | ✅ | 4 registros |
| stefano.learning_rules | ✅ | 61 registros |
| stefano.nurturing_followups | ✅ | 0 registros |

## Warnings
- ⚠️ Tablas extra en DB (no en modelos): {'creator_calibrations', 'content_embeddings', 'leads_backup_20260204'}
