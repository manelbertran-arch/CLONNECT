"""Test dna_update_triggers integration in dm_agent_v2 (Step 13)."""


class TestDNATriggersIntegration:
    def test_module_importable(self):
        from services.dna_update_triggers import get_dna_triggers

        triggers = get_dna_triggers()
        assert triggers is not None

    def test_flag_exists(self):
        from core.dm_agent_v2 import ENABLE_DNA_TRIGGERS

        assert isinstance(ENABLE_DNA_TRIGGERS, bool)

    def test_first_analysis_threshold(self):
        from services.dna_update_triggers import get_dna_triggers

        triggers = get_dna_triggers()
        assert not triggers.should_update(None, 3)  # Below min
        assert triggers.should_update(None, 5)  # At min

    def test_no_update_during_cooldown(self):
        from datetime import datetime, timezone

        from services.dna_update_triggers import get_dna_triggers

        triggers = get_dna_triggers()
        dna = {
            "total_messages_analyzed": 10,
            "last_analyzed_at": datetime.now(timezone.utc).isoformat(),
        }
        assert not triggers.should_update(dna, 15)  # Within cooldown
