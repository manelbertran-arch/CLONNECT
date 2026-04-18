"""Gate functions for BudgetOrchestrator sections.

Each gate receives a _ContextAssemblyInputs instance and returns
Optional[Section]. Gates are async to support asyncio.wait_for timeout.
"""
from core.dm.budget.gates import fewshots, history, rag, style

__all__ = ["style", "fewshots", "rag", "history"]
