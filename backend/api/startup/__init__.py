"""
api.startup package — Application startup handlers.

Re-exports ``register_startup_handlers`` so that existing imports
(``from api.startup import register_startup_handlers``) continue to work.
"""

from api.startup.handlers import register_startup_handlers

__all__ = ["register_startup_handlers"]
