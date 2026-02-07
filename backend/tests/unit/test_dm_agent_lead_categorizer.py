"""Test lead_categorizer integration in dm_agent_v2 (Step 8)."""


class TestLeadCategorizerIntegration:
    def test_module_importable(self):
        from core.lead_categorizer import get_lead_categorizer

        categorizer = get_lead_categorizer()
        assert categorizer is not None

    def test_flag_exists(self):
        from core.dm_agent_v2 import ENABLE_LEAD_CATEGORIZER

        assert isinstance(ENABLE_LEAD_CATEGORIZER, bool)

    def test_new_lead(self):
        from core.lead_categorizer import LeadCategory, get_lead_categorizer

        categorizer = get_lead_categorizer()
        messages = [{"role": "user", "content": "Hola"}]
        category, score, reason = categorizer.categorize(messages)
        assert category == LeadCategory.NUEVO

    def test_hot_lead(self):
        from core.lead_categorizer import LeadCategory, get_lead_categorizer

        categorizer = get_lead_categorizer()
        messages = [
            {"role": "user", "content": "¿Cuánto cuesta el curso?"},
            {"role": "user", "content": "Quiero comprarlo, pásame el link de pago"},
        ]
        category, score, reason = categorizer.categorize(messages)
        assert category == LeadCategory.CALIENTE

    def test_customer(self):
        from core.lead_categorizer import LeadCategory, get_lead_categorizer

        categorizer = get_lead_categorizer()
        messages = [{"role": "user", "content": "Ya lo compré"}]
        category, score, reason = categorizer.categorize(messages, is_customer=True)
        assert category == LeadCategory.CLIENTE
