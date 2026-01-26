"""
Intelligence Engine - Business Intelligence and Predictive Analytics for Clonnect.

Provides:
- Pattern analysis (temporal, conversation, content, conversion)
- Predictions (conversion, churn, revenue)
- Recommendations (content, actions, products)
- Weekly reports with LLM-generated insights
"""

from .engine import IntelligenceEngine, ENABLE_INTELLIGENCE

__all__ = ['IntelligenceEngine', 'ENABLE_INTELLIGENCE']
