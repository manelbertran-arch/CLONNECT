"""
Módulos de razonamiento avanzado para Clonnect.

Incluye:
- SelfConsistency: Verificación por consenso (anti-alucinación)
- ChainOfThought: Razonamiento paso a paso
- Reflexion: Autocrítica iterativa
"""

from .self_consistency import SelfConsistency
from .chain_of_thought import ChainOfThought
from .reflexion import Reflexion

__all__ = ["SelfConsistency", "ChainOfThought", "Reflexion"]
