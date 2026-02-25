"""
Sync endpoints — decomposed into focused modules.

- sync_dm.py: DM sync operations
- sync_fixes.py: One-off fixes and migrations
- sync_media.py: Media and thumbnail operations
- sync_backup.py: Backup operations
- sync_ingestion.py: Ingestion testing

Import the individual routers from the admin __init__.py.
"""
