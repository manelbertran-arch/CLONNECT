"""
Personality Extraction Engine — Universal Conversational Intelligence System

Analyzes a creator's complete DM history to extract their conversational DNA
and generate bot configuration (system prompt, templates, copilot rules).

Pipeline:
  Phase 0: Data cleaning (filter bot messages from human)
  Phase 1: Doc A — Raw conversations segregated by lead
  Phase 2: Doc B — Individual analysis per lead
  Phase 3: Doc C — Personality Profile (conversational DNA)
  Phase 4: Doc D — System prompt + blacklist + template pool
  Phase 5: Doc E — Copilot rules (AUTO / DRAFT / MANUAL)
"""

from core.personality_extraction.extractor import PersonalityExtractor

__all__ = ["PersonalityExtractor"]
