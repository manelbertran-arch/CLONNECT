#!/usr/bin/env python3
"""
Query expansion para mejorar búsqueda RAG.
Migrado de clonnect-memory-engine y adaptado para Clonnect Creators.

Optimizado para:
- Infoproductos (cursos, mentorías, ebooks)
- Creadores de contenido
- Ventas en español

Beneficios:
- +15-25% recall en búsquedas
- Captura variaciones de lenguaje
- 100% local, sin coste
"""
from typing import List, Set
import re


class QueryExpander:
    """
    Expande queries con sinónimos y variaciones para mejorar recall.

    Técnicas:
    - Sinónimos específicos de infoproductos
    - Expansión de acrónimos
    - Variaciones coloquiales en español
    """

    def __init__(self):
        # Sinónimos específicos para creadores/infoproductos
        self.synonyms = {
            # Productos
            "curso": ["programa", "formación", "training", "masterclass", "bootcamp"],
            "mentoría": ["mentoring", "coaching", "acompañamiento", "asesoría"],
            "ebook": ["libro", "guía", "manual", "pdf"],
            "plantilla": ["template", "recurso", "herramienta"],
            "masterclass": ["clase magistral", "webinar", "taller"],

            # Precio/Pago
            "precio": ["coste", "costo", "valor", "inversión", "cuánto cuesta", "cuanto vale"],
            "pagar": ["comprar", "adquirir", "invertir", "apuntarme"],
            "caro": ["costoso", "elevado", "mucho dinero"],
            "barato": ["económico", "asequible", "accesible"],
            "descuento": ["oferta", "promoción", "rebaja", "cupón"],
            "gratis": ["gratuito", "free", "sin coste", "regalo"],

            # Tiempo
            "tiempo": ["duración", "horas", "semanas"],
            "rápido": ["corto", "breve", "intensivo"],
            "flexible": ["a tu ritmo", "sin horarios"],

            # Beneficios
            "resultados": ["beneficios", "logros", "éxito"],
            "aprender": ["dominar", "entender", "conocer"],
            "ganar": ["facturar", "ingresar", "monetizar"],
            "escalar": ["crecer", "expandir", "multiplicar"],

            # Objeciones
            "funciona": ["sirve", "vale la pena", "merece"],
            "garantía": ["devolución", "reembolso"],
            "soporte": ["ayuda", "asistencia", "dudas"],

            # Acciones
            "comprar": ["adquirir", "obtener", "conseguir", "apuntarme"],
            "empezar": ["comenzar", "iniciar", "arrancar"],
            "inscribir": ["registrar", "apuntar", "matricular"],

            # Contenido
            "módulo": ["lección", "clase", "tema", "unidad"],
            "vídeo": ["video", "grabación", "contenido"],
            "material": ["recursos", "contenido", "documentación"],

            # Personas
            "alumno": ["estudiante", "participante", "miembro"],
            "cliente": ["comprador", "usuario"],
            "experto": ["profesional", "especialista", "crack"],
        }

        # Acrónimos comunes
        self.acronyms = {
            "ia": "inteligencia artificial",
            "ai": "inteligencia artificial",
            "ml": "machine learning",
            "saas": "software as a service",
            "b2b": "business to business",
            "b2c": "business to consumer",
            "roi": "retorno de inversión",
            "kpi": "indicador clave",
            "crm": "gestión de clientes",
            "faq": "preguntas frecuentes",
        }

    def expand(self, query: str, max_expansions: int = 3) -> List[str]:
        """
        Expande query con sinónimos y variaciones.

        Args:
            query: Query original
            max_expansions: Máximo de variaciones a generar

        Returns:
            Lista de queries expandidas (incluye original)
        """
        if not query or not query.strip():
            return [query]

        expanded_queries = [query]
        query_lower = query.lower()

        # 1. Expandir acrónimos
        for acronym, expansion in self.acronyms.items():
            if acronym in query_lower.split():
                expanded = query_lower.replace(acronym, expansion)
                if expanded not in expanded_queries:
                    expanded_queries.append(expanded)
                if len(expanded_queries) >= max_expansions + 1:
                    return expanded_queries

        # 2. Expandir sinónimos
        words = re.findall(r'\b\w+\b', query_lower)
        for word in words:
            if word in self.synonyms:
                for synonym in self.synonyms[word][:2]:
                    expanded = query_lower.replace(word, synonym)
                    if expanded not in expanded_queries:
                        expanded_queries.append(expanded)
                    if len(expanded_queries) >= max_expansions + 1:
                        return expanded_queries

        return expanded_queries[:max_expansions + 1]

    def expand_tokens(self, query: str) -> Set[str]:
        """
        Expande query en conjunto de tokens únicos.

        Args:
            query: Query original

        Returns:
            Set de tokens expandidos
        """
        expanded_queries = self.expand(query, max_expansions=5)
        all_tokens = set()

        for q in expanded_queries:
            tokens = re.findall(r'\b\w+\b', q.lower())
            all_tokens.update(tokens)

        return all_tokens

    def add_synonym(self, term: str, synonyms: List[str]):
        """Añade sinónimos custom al diccionario"""
        term_lower = term.lower()
        if term_lower in self.synonyms:
            self.synonyms[term_lower].extend(synonyms)
        else:
            self.synonyms[term_lower] = synonyms

    def add_acronym(self, acronym: str, expansion: str):
        """Añade acrónimo custom al diccionario"""
        self.acronyms[acronym.lower()] = expansion.lower()


# Instancia global
_query_expander = None


def get_query_expander() -> QueryExpander:
    """Get global query expander instance"""
    global _query_expander
    if _query_expander is None:
        _query_expander = QueryExpander()
    return _query_expander
