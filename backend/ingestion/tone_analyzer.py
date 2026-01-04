"""
Tone Analyzer - Analiza y extrae el estilo unico del creador.
Fase 1 - Magic Slice

Este modulo es el corazon del WOW #2: "Es igualito a como habla"
"""

import json
import logging
import re
from typing import List, Dict, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime
from collections import Counter

logger = logging.getLogger(__name__)


@dataclass
class ToneProfile:
    """
    Perfil de tono/voz del creador.
    Se usa para que el bot replique su estilo exacto.
    """
    creator_id: str

    # Estilo general
    formality: str = 'neutral'  # 'muy_formal', 'formal', 'neutral', 'informal', 'muy_informal'
    energy: str = 'media'  # 'muy_alta', 'alta', 'media', 'baja', 'muy_baja'
    warmth: str = 'calido'  # 'muy_calido', 'calido', 'neutral', 'distante', 'muy_distante'

    # Vocabulario caracteristico
    signature_phrases: List[str] = field(default_factory=list)  # "vamos crack", "a tope", etc.
    common_greetings: List[str] = field(default_factory=list)  # "Hey!", "Hola guapa", etc.
    common_closings: List[str] = field(default_factory=list)  # "Un abrazo", "Nos vemos", etc.
    filler_words: List[str] = field(default_factory=list)  # "pues", "bueno", "mira", etc.

    # Emojis
    uses_emojis: bool = True
    favorite_emojis: List[str] = field(default_factory=list)
    emoji_frequency: str = 'media'  # 'ninguna', 'baja', 'media', 'alta', 'muy_alta'

    # Formato
    uses_caps_emphasis: bool = False  # USA MAYUSCULAS para enfatizar
    uses_ellipsis: bool = False  # Usa puntos suspensivos...
    average_message_length: str = 'media'  # 'muy_corta', 'corta', 'media', 'larga', 'muy_larga'
    uses_line_breaks: bool = True  # Separa ideas en lineas

    # Idioma
    primary_language: str = 'es'
    uses_anglicisms: bool = False  # "cool", "random", "flow"
    regional_expressions: List[str] = field(default_factory=list)  # Expresiones locales

    # Comportamiento conversacional
    asks_questions: bool = True  # Hace preguntas al seguidor
    uses_humor: bool = False
    directness: str = 'media'  # 'muy_directa', 'directa', 'media', 'indirecta', 'muy_indirecta'

    # Temas y valores (detectados del contenido)
    main_topics: List[str] = field(default_factory=list)
    values_expressed: List[str] = field(default_factory=list)

    # Metadata
    analyzed_posts_count: int = 0
    last_updated: datetime = field(default_factory=datetime.utcnow)
    confidence_score: float = 0.0  # 0-1, basado en cantidad de datos

    def to_system_prompt_section(self) -> str:
        """
        Genera la seccion del system prompt que define el tono.
        Se inyecta en cada llamada al LLM.
        """
        prompt_parts = []

        # Estilo base
        prompt_parts.append("ESTILO DE COMUNICACION:")
        prompt_parts.append(f"- Nivel de formalidad: {self.formality}")
        prompt_parts.append(f"- Energia: {self.energy}")
        prompt_parts.append(f"- Calidez: {self.warmth}")
        prompt_parts.append(f"- Nivel de directness: {self.directness}")

        # Frases caracteristicas
        if self.signature_phrases:
            prompt_parts.append("\nFRASES CARACTERISTICAS que usa frecuentemente:")
            for phrase in self.signature_phrases[:10]:
                prompt_parts.append(f'  - "{phrase}"')

        # Saludos
        if self.common_greetings:
            prompt_parts.append("\nFORMAS DE SALUDAR:")
            for greeting in self.common_greetings[:5]:
                prompt_parts.append(f'  - "{greeting}"')

        # Despedidas
        if self.common_closings:
            prompt_parts.append("\nFORMAS DE DESPEDIRSE:")
            for closing in self.common_closings[:5]:
                prompt_parts.append(f'  - "{closing}"')

        # Muletillas
        if self.filler_words:
            prompt_parts.append("\nMULETILLAS que usa:")
            prompt_parts.append(f"  {', '.join(self.filler_words[:10])}")

        # Emojis
        prompt_parts.append("\nUSO DE EMOJIS:")
        if self.uses_emojis and self.favorite_emojis:
            prompt_parts.append(f"  - Frecuencia: {self.emoji_frequency}")
            prompt_parts.append(f"  - Emojis favoritos: {' '.join(self.favorite_emojis[:10])}")
        else:
            prompt_parts.append("  - No usa emojis o muy raramente")

        # Formato
        prompt_parts.append("\nFORMATO DE MENSAJES:")
        prompt_parts.append(f"  - Longitud tipica: {self.average_message_length}")
        if self.uses_caps_emphasis:
            prompt_parts.append("  - USA MAYUSCULAS para enfatizar")
        if self.uses_ellipsis:
            prompt_parts.append("  - Usa puntos suspensivos...")
        if self.uses_line_breaks:
            prompt_parts.append("  - Separa ideas en diferentes lineas")

        # Comportamiento
        prompt_parts.append("\nCOMPORTAMIENTO:")
        if self.asks_questions:
            prompt_parts.append("  - Hace preguntas para conocer mejor al seguidor")
        if self.uses_humor:
            prompt_parts.append("  - Usa humor de forma natural")
        if self.uses_anglicisms:
            prompt_parts.append("  - Mezcla palabras en ingles de forma natural")

        # Expresiones regionales
        if self.regional_expressions:
            prompt_parts.append("\nEXPRESIONES REGIONALES:")
            for expr in self.regional_expressions[:5]:
                prompt_parts.append(f'  - "{expr}"')

        # Temas
        if self.main_topics:
            prompt_parts.append("\nTEMAS PRINCIPALES sobre los que habla:")
            prompt_parts.append(f"  {', '.join(self.main_topics[:10])}")

        return "\n".join(prompt_parts)

    def to_dict(self) -> Dict:
        """Convierte a diccionario para guardar en DB."""
        data = asdict(self)
        data['last_updated'] = self.last_updated.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict) -> 'ToneProfile':
        """Crea desde diccionario."""
        if 'last_updated' in data and isinstance(data['last_updated'], str):
            data['last_updated'] = datetime.fromisoformat(data['last_updated'])
        return cls(**data)


class ToneAnalyzer:
    """
    Analiza contenido del creador para extraer su perfil de tono.
    """

    # Prompt para el analisis con LLM
    ANALYSIS_PROMPT = '''Analiza los siguientes posts de un creador de contenido y extrae su estilo de comunicacion unico.

POSTS DEL CREADOR:
{posts_text}

---

Analiza y responde en JSON con esta estructura exacta:
{{
    "formality": "muy_formal|formal|neutral|informal|muy_informal",
    "energy": "muy_alta|alta|media|baja|muy_baja",
    "warmth": "muy_calido|calido|neutral|distante|muy_distante",
    "directness": "muy_directa|directa|media|indirecta|muy_indirecta",
    "signature_phrases": ["frase1", "frase2", ...],
    "common_greetings": ["saludo1", "saludo2", ...],
    "common_closings": ["despedida1", "despedida2", ...],
    "filler_words": ["muletilla1", "muletilla2", ...],
    "uses_emojis": true|false,
    "favorite_emojis": ["emoji1", "emoji2", ...],
    "emoji_frequency": "ninguna|baja|media|alta|muy_alta",
    "uses_caps_emphasis": true|false,
    "uses_ellipsis": true|false,
    "average_message_length": "muy_corta|corta|media|larga|muy_larga",
    "uses_line_breaks": true|false,
    "uses_anglicisms": true|false,
    "regional_expressions": ["expresion1", "expresion2", ...],
    "asks_questions": true|false,
    "uses_humor": true|false,
    "main_topics": ["tema1", "tema2", ...],
    "values_expressed": ["valor1", "valor2", ...]
}}

IMPORTANTE:
- Extrae FRASES EXACTAS que usa el creador, no las inventes
- Los emojis deben ser los que realmente usa
- Se especifico con las expresiones regionales
- Solo responde con el JSON, sin explicaciones'''

    def __init__(self, llm_client=None):
        """
        Args:
            llm_client: Cliente LLM (Groq, OpenAI, etc.). Si None, usa el default.
        """
        self.llm_client = llm_client

    async def analyze(
        self,
        creator_id: str,
        posts: List[Dict],  # Lista de posts con 'caption' como minimo
        max_posts: int = 30
    ) -> ToneProfile:
        """
        Analiza posts del creador y genera su ToneProfile.

        Args:
            creator_id: ID del creador
            posts: Lista de posts (dicts con 'caption')
            max_posts: Maximo de posts a analizar (para no exceder contexto)

        Returns:
            ToneProfile del creador
        """
        # Filtrar posts con contenido
        valid_posts = [p for p in posts if p.get('caption') and len(p['caption']) > 20]

        if not valid_posts:
            logger.warning(f"No hay posts validos para analizar para creator {creator_id}")
            return self._create_default_profile(creator_id)

        # Limitar cantidad
        posts_to_analyze = valid_posts[:max_posts]

        # Preparar texto para analisis
        posts_text = self._prepare_posts_text(posts_to_analyze)

        # Analisis estadistico basico (no necesita LLM)
        stats = self._analyze_statistics(posts_to_analyze)

        # Analisis con LLM
        llm_analysis = await self._analyze_with_llm(posts_text)

        # Combinar analisis
        profile = self._merge_analyses(creator_id, stats, llm_analysis, len(posts_to_analyze))

        logger.info(f"ToneProfile generado para creator {creator_id} con {len(posts_to_analyze)} posts")
        return profile

    def analyze_sync(
        self,
        creator_id: str,
        posts: List[Dict],
        max_posts: int = 30
    ) -> ToneProfile:
        """Version sincrona de analyze()."""
        import asyncio
        return asyncio.run(self.analyze(creator_id, posts, max_posts))

    def _prepare_posts_text(self, posts: List[Dict]) -> str:
        """Prepara el texto de posts para el prompt."""
        lines = []
        for i, post in enumerate(posts, 1):
            caption = post.get('caption', '').strip()
            if caption:
                lines.append(f"POST {i}:\n{caption}\n")
        return "\n---\n".join(lines)

    def _analyze_statistics(self, posts: List[Dict]) -> Dict:
        """Analisis estadistico que no necesita LLM."""
        stats = {
            'total_posts': len(posts),
            'emojis': [],
            'hashtags': [],
            'mentions': [],
            'avg_length': 0,
            'uses_caps': False,
            'uses_ellipsis': False,
            'uses_line_breaks': False,
            'question_marks': 0
        }

        total_length = 0
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # emoticons
            "\U0001F300-\U0001F5FF"  # symbols & pictographs
            "\U0001F680-\U0001F6FF"  # transport & map symbols
            "\U0001F1E0-\U0001F1FF"  # flags
            "\U00002702-\U000027B0"
            "\U000024C2-\U0001F251"
            "]+",
            flags=re.UNICODE
        )

        for post in posts:
            caption = post.get('caption', '')
            total_length += len(caption)

            # Emojis
            emojis = emoji_pattern.findall(caption)
            stats['emojis'].extend(emojis)

            # Hashtags y menciones
            stats['hashtags'].extend(re.findall(r'#(\w+)', caption))
            stats['mentions'].extend(re.findall(r'@(\w+)', caption))

            # Patrones de formato
            if re.search(r'[A-Z]{3,}', caption):  # 3+ mayusculas seguidas
                stats['uses_caps'] = True
            if '...' in caption or '...' in caption:
                stats['uses_ellipsis'] = True
            if '\n' in caption:
                stats['uses_line_breaks'] = True

            # Preguntas
            stats['question_marks'] += caption.count('?')

        stats['avg_length'] = total_length / len(posts) if posts else 0

        # Contar frecuencias
        stats['emoji_counts'] = Counter(stats['emojis']).most_common(15)
        stats['hashtag_counts'] = Counter(stats['hashtags']).most_common(10)

        return stats

    async def _analyze_with_llm(self, posts_text: str) -> Dict:
        """Analiza con LLM para extraer patrones de lenguaje."""
        prompt = self.ANALYSIS_PROMPT.format(posts_text=posts_text)

        try:
            if self.llm_client:
                # Usar cliente proporcionado
                response = await self.llm_client.chat(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3
                )
                response_text = response.get('content', '{}')
            else:
                # Fallback: intentar importar cliente default de Clonnect
                try:
                    from backend.core.llm_client import get_llm_client
                    client = get_llm_client()
                    response_text = await client.generate(prompt, temperature=0.3)
                except ImportError:
                    logger.warning("No LLM client available, using defaults")
                    return {}

            # Parsear JSON de respuesta
            # Limpiar posible markdown
            response_text = response_text.strip()
            if response_text.startswith('```'):
                response_text = re.sub(r'^```json?\n?', '', response_text)
                response_text = re.sub(r'\n?```$', '', response_text)

            return json.loads(response_text)

        except json.JSONDecodeError as e:
            logger.error(f"Error parseando respuesta LLM: {e}")
            return {}
        except Exception as e:
            logger.error(f"Error en analisis LLM: {e}")
            return {}

    def _merge_analyses(
        self,
        creator_id: str,
        stats: Dict,
        llm_analysis: Dict,
        posts_count: int
    ) -> ToneProfile:
        """Combina analisis estadistico y LLM en un ToneProfile."""

        # Determinar frecuencia de emojis basado en estadisticas
        emoji_per_post = len(stats['emojis']) / posts_count if posts_count else 0
        if emoji_per_post == 0:
            emoji_freq = 'ninguna'
        elif emoji_per_post < 1:
            emoji_freq = 'baja'
        elif emoji_per_post < 3:
            emoji_freq = 'media'
        elif emoji_per_post < 6:
            emoji_freq = 'alta'
        else:
            emoji_freq = 'muy_alta'

        # Determinar longitud promedio
        avg_len = stats['avg_length']
        if avg_len < 50:
            msg_length = 'muy_corta'
        elif avg_len < 150:
            msg_length = 'corta'
        elif avg_len < 400:
            msg_length = 'media'
        elif avg_len < 800:
            msg_length = 'larga'
        else:
            msg_length = 'muy_larga'

        # Calcular confidence score
        if posts_count >= 30:
            confidence = 0.95
        elif posts_count >= 20:
            confidence = 0.85
        elif posts_count >= 10:
            confidence = 0.70
        elif posts_count >= 5:
            confidence = 0.50
        else:
            confidence = 0.30

        # Extraer emojis favoritos de estadisticas
        favorite_emojis = [emoji for emoji, count in stats.get('emoji_counts', [])]

        return ToneProfile(
            creator_id=creator_id,
            # Del LLM
            formality=llm_analysis.get('formality', 'neutral'),
            energy=llm_analysis.get('energy', 'media'),
            warmth=llm_analysis.get('warmth', 'calido'),
            directness=llm_analysis.get('directness', 'media'),
            signature_phrases=llm_analysis.get('signature_phrases', []),
            common_greetings=llm_analysis.get('common_greetings', []),
            common_closings=llm_analysis.get('common_closings', []),
            filler_words=llm_analysis.get('filler_words', []),
            uses_anglicisms=llm_analysis.get('uses_anglicisms', False),
            regional_expressions=llm_analysis.get('regional_expressions', []),
            asks_questions=llm_analysis.get('asks_questions', stats['question_marks'] > posts_count * 0.3),
            uses_humor=llm_analysis.get('uses_humor', False),
            main_topics=llm_analysis.get('main_topics', []),
            values_expressed=llm_analysis.get('values_expressed', []),
            # De estadisticas
            uses_emojis=len(stats['emojis']) > 0,
            favorite_emojis=favorite_emojis or llm_analysis.get('favorite_emojis', []),
            emoji_frequency=emoji_freq,
            uses_caps_emphasis=stats['uses_caps'],
            uses_ellipsis=stats['uses_ellipsis'],
            average_message_length=msg_length,
            uses_line_breaks=stats['uses_line_breaks'],
            # Metadata
            analyzed_posts_count=posts_count,
            confidence_score=confidence,
            last_updated=datetime.utcnow()
        )

    def _create_default_profile(self, creator_id: str) -> ToneProfile:
        """Crea perfil por defecto cuando no hay datos."""
        return ToneProfile(
            creator_id=creator_id,
            formality='informal',
            energy='alta',
            warmth='calido',
            directness='directa',
            confidence_score=0.0
        )


# =============================================================================
# UTILIDADES
# =============================================================================

def quick_analyze_text(text: str) -> Dict:
    """
    Analisis rapido de un texto sin LLM.
    Util para analizar mensajes individuales.
    """
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF"
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "]+",
        flags=re.UNICODE
    )

    return {
        'length': len(text),
        'word_count': len(text.split()),
        'emoji_count': len(emoji_pattern.findall(text)),
        'has_questions': '?' in text,
        'has_exclamations': '!' in text,
        'has_caps_emphasis': bool(re.search(r'[A-Z]{3,}', text)),
        'has_ellipsis': '...' in text or '...' in text,
        'hashtag_count': len(re.findall(r'#\w+', text)),
        'mention_count': len(re.findall(r'@\w+', text))
    }
