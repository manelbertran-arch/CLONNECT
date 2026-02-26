# CAPA 2 — Unit Tests

**Fecha**: 2026-02-26 06:54 UTC

## Resultado: 105/105 PASS (100%)

| Archivo | Tests | PASS | FAIL | Módulo cubierto |
|---------|-------|------|------|-----------------|
| test_lead_scoring_unit.py | 33 | ✅ 33 | 0 | services/lead_scoring.py |
| test_dm_phases_unit.py | 14 | ✅ 14 | 0 | core/dm/phases/detection.py, text_utils.py |
| test_webhook_unit.py | 16 | ✅ 16 | 0 | core/webhook_routing.py |
| test_copilot_unit.py | 22 | ✅ 22 | 0 | api/routers/copilot/actions.py, core/copilot_service.py |
| test_payments_unit.py | 20 | ✅ 20 | 0 | api/routers/payments.py, core/payments.py |
| **TOTAL** | **105** | **✅ 105** | **0** | |

---

### test_lead_scoring_unit.py — 33 tests

| Group | Tests | Cobertura |
|-------|-------|-----------|
| TestClassifyLead | 12 | classify_lead() — todos los 7 paths de clasificación |
| TestCalculateScore | 11 | calculate_score() — todas las 6 categorías + edge cases |
| TestKeywordLists | 10 | FOLLOWER_PURCHASE/INTEREST/SOCIAL/NEGATIVE/COLLABORATION keywords + SCORE_RANGES |

Key validations:
- `cliente` preservado aunque haya señales de compra nuevas
- `caliente` requiere ≥2 purchase_hits ó purchase+scheduling
- `colaborador` requiere ≥2 collaboration_hits
- `amigo` requiere señales sociales bidireccionales
- `frío` requiere inactividad ≥14 días + actividad previa (≥2 mensajes)
- Score siempre dentro del rango definido en SCORE_RANGES
- Keywords negativos reducen score de `caliente`
- Score nunca < 0 ni > 100

---

### test_dm_phases_unit.py — 14 tests

| Group | Tests | Cobertura |
|-------|-------|-----------|
| TestSensitiveDetector | 3 | detect_sensitive_content(), get_crisis_resources() |
| TestContextDetector | 2 | detect_all() smoke test |
| TestDMModels | 3 | DetectionResult, DMResponse construction |
| TestTextUtils | 2 | _message_mentions_product() (fuzzy, accent-insensitive) |
| TestPhaseDetectionMocked | 2 | phase_detection() — normal + crisis path (mocked) |
| TestPostprocessingHelpers | 2 | phase_postprocessing import smoke |

---

### test_webhook_unit.py — 16 tests

| Group | Tests | Cobertura |
|-------|-------|-----------|
| TestWebhookRouting | 5 | extract_all_instagram_ids(), find_creator_for_webhook() |
| TestWebhookPayloadValidation | 4 | Estructura válida/inválida de payload Meta |
| TestEchoDetection | 3 | Lógica de filtrado de mensajes echo |
| TestAuthHeaders | 2 | api.auth import, X-Hub-Signature-256 format |
| TestSaveUnmatchedWebhook | 2 | save_unmatched_webhook() import + graceful error |

---

### test_copilot_unit.py — 22 tests

| Group | Tests | Cobertura |
|-------|-------|-----------|
| TestCopilotModels | 9 | ApproveRequest, ToggleRequest, DiscardRequest, ManualResponseRequest |
| TestCopilotService | 7 | get_copilot_service() singleton, interfaz pública |
| TestEditDiff | 3 | _calculate_edit_diff() — identical, different, value |
| TestPendingResponseFormat | 3 | Estructuras de respuesta pending/approve/discard |

---

### test_payments_unit.py — 20 tests

| Group | Tests | Cobertura |
|-------|-------|-----------|
| TestPurchaseRecordSchema | 4 | PurchaseRecord Pydantic model |
| TestPaymentManager | 4 | get_payment_manager(), métodos requeridos |
| TestSalesTracker | 4 | get_sales_tracker(), get_stats(), record_sale() |
| TestRevenueCalculation | 6 | avg_order_value, totales combinados, daily_revenue |
| TestPurchaseAttribution | 2 | attribute_sale_to_bot() success/not-found |

---

## ✅ CAPA 2 PASS — 105/105 (100%)
