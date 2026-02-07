"""Test message_splitter integration in dm_agent_v2 (Step 18)."""


class TestMessageSplitIntegration:
    def test_flag_exists(self):
        from core.dm_agent_v2 import ENABLE_MESSAGE_SPLITTING

        assert isinstance(ENABLE_MESSAGE_SPLITTING, bool)

    def test_import_works(self):
        from services.message_splitter import get_message_splitter

        splitter = get_message_splitter()
        assert hasattr(splitter, "should_split")
        assert hasattr(splitter, "split")

    def test_short_message_no_split(self):
        from services.message_splitter import get_message_splitter

        splitter = get_message_splitter()
        assert not splitter.should_split("Hola!")

    def test_long_message_splits(self):
        from services.message_splitter import get_message_splitter

        splitter = get_message_splitter()
        long_msg = "Mira, te cuento sobre el curso. " * 10
        if splitter.should_split(long_msg):
            parts = splitter.split(long_msg)
            assert len(parts) >= 2
            for part in parts:
                assert hasattr(part, "text")
                assert hasattr(part, "delay_before")
