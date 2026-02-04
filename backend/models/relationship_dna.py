"""RelationshipDNA models for personalized communication per lead.

This module contains the data models for storing relationship-specific
context between creators and their leads, enabling personalized
communication style based on relationship type.

Part of RELATIONSHIP-DNA feature.
"""
from enum import Enum


class RelationshipType(str, Enum):
    """Types of relationships between creator and lead.

    Used to determine communication style and vocabulary.
    Each type has specific vocabulary rules:

    - INTIMA: Romantic/very close - uses 💙, vulnerable tone, no "hermano"
    - AMISTAD_CERCANA: Close friend - uses "hermano", "bro", spiritual tone
    - AMISTAD_CASUAL: Casual friend - uses "crack", light and fun tone
    - CLIENTE: Client/prospect - informative, helpful, professional but warm
    - COLABORADOR: Business partner - professional, respectful
    - DESCONOCIDO: New lead - neutral, no assumptions
    """

    INTIMA = "INTIMA"
    AMISTAD_CERCANA = "AMISTAD_CERCANA"
    AMISTAD_CASUAL = "AMISTAD_CASUAL"
    CLIENTE = "CLIENTE"
    COLABORADOR = "COLABORADOR"
    DESCONOCIDO = "DESCONOCIDO"
