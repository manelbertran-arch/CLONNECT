"""Tests for DNA migration script for existing leads.

TDD: Tests written FIRST before implementation.
Part of RELATIONSHIP-DNA feature.

Migration script analyzes existing conversations and creates DNA for leads.
"""

from unittest.mock import patch



class TestMigrateExistingLeads:
    """Test suite for DNA migration script."""

    def test_migrate_existing_leads(self):
        """Should analyze and create DNA for existing leads."""
        from scripts.migrate_dna import DNAMigrator

        migrator = DNAMigrator()

        with patch.object(migrator, "_get_leads_with_messages") as mock_leads:
            with patch.object(migrator, "_analyze_and_create_dna") as mock_analyze:
                # Mock leads with messages
                mock_leads.return_value = [
                    {"creator_id": "stefan", "follower_id": "lead1", "message_count": 50},
                    {"creator_id": "stefan", "follower_id": "lead2", "message_count": 30},
                ]
                mock_analyze.return_value = True

                result = migrator.migrate("stefan")

                assert result["processed"] == 2
                assert result["success"] == 2
                assert mock_analyze.call_count == 2

    def test_analyze_top_conversations(self):
        """Should prioritize leads with most messages."""
        from scripts.migrate_dna import DNAMigrator

        migrator = DNAMigrator()

        with patch.object(migrator, "_get_leads_with_messages") as mock_leads:
            with patch.object(migrator, "_analyze_and_create_dna") as mock_analyze:
                # Mock leads with varying message counts
                mock_leads.return_value = [
                    {"creator_id": "stefan", "follower_id": "vip", "message_count": 200},
                    {"creator_id": "stefan", "follower_id": "active", "message_count": 100},
                    {"creator_id": "stefan", "follower_id": "normal", "message_count": 50},
                ]
                mock_analyze.return_value = True

                # Only migrate top 2
                result = migrator.migrate("stefan", limit=2)

                assert result["processed"] == 2
                # VIP (200 msgs) should be processed first
                assert mock_analyze.call_args_list[0][0][0]["follower_id"] == "vip"

    def test_skip_low_message_leads(self):
        """Should skip leads with insufficient messages."""
        from scripts.migrate_dna import DNAMigrator

        migrator = DNAMigrator()

        with patch.object(migrator, "_get_leads_with_messages") as mock_leads:
            with patch.object(migrator, "_analyze_and_create_dna") as mock_analyze:
                # Mix of leads with varying message counts
                mock_leads.return_value = [
                    {"creator_id": "stefan", "follower_id": "active", "message_count": 50},
                    {"creator_id": "stefan", "follower_id": "new1", "message_count": 3},
                    {"creator_id": "stefan", "follower_id": "new2", "message_count": 2},
                ]
                mock_analyze.return_value = True

                result = migrator.migrate("stefan", min_messages=5)

                # Only 1 lead has >= 5 messages
                assert result["processed"] == 1
                assert result["skipped"] == 2
                mock_analyze.assert_called_once()
