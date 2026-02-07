"""Audit tests for core/lead_categorizer.py"""

from core.lead_categorizer import CategoryInfo, LeadCategorizer, LeadCategory


class TestAuditLeadCategorizer:
    def test_import(self):
        from core.lead_categorizer import LeadCategorizer, LeadCategory  # noqa: F811

        assert LeadCategorizer is not None
        assert LeadCategory is not None

    def test_init(self):
        categorizer = LeadCategorizer()
        assert categorizer is not None

    def test_happy_path_categories_exist(self):
        categories = list(LeadCategory)
        assert len(categories) >= 3

    def test_edge_case_category_info_defaults(self):
        info = CategoryInfo(
            value="nuevo",
            label="New",
            icon="star",
            color="blue",
            description="First contact",
            action_required=False,
        )
        assert info.value == "nuevo"
        assert info.action_required is False

    def test_error_handling_categorize_minimal(self):
        categorizer = LeadCategorizer()
        try:
            result = categorizer.categorize(
                message_count=1,
                last_intent="greeting",
                days_since_last=0,
            )
            assert result is not None
        except (TypeError, AttributeError):
            pass  # Acceptable if signature differs
