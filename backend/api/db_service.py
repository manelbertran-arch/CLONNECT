"""
Backward compatibility shim — all functions moved to api.services.db_service.

This file previously contained duplicate implementations of database functions.
All canonical implementations now live in api.services.db_service.
This thin wrapper re-exports everything so existing imports continue to work.
"""
from api.services.db_service import *  # noqa: F401,F403
