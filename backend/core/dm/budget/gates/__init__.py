"""Gate functions for BudgetOrchestrator sections.

Each gate receives a _ContextAssemblyInputs instance and returns
Optional[Section]. Gates are async to support asyncio.wait_for timeout.

A1.2 gates: style, fewshots, rag, history
A1.4 gates: memory, audio, commitments, dna
"""
from core.dm.budget.gates import audio, commitments, dna, fewshots, history, memory, rag, style

__all__ = ["style", "fewshots", "rag", "history", "memory", "audio", "commitments", "dna"]
