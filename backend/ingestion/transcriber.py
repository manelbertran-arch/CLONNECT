"""
Transcriber - Convierte audio/video a texto usando Whisper.

Soporta:
- Archivos de audio locales (mp3, wav, m4a, ogg)
- Archivos de video locales (mp4, mov, webm)
- URLs de audio/video
- Timestamps para citaciones

Dependencias:
- openai (Whisper API)
- httpx (para descargas)
"""

import logging
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class AudioFormat(str, Enum):
    """Formatos de audio soportados."""

    MP3 = "mp3"
    WAV = "wav"
    M4A = "m4a"
    OGG = "ogg"
    WEBM = "webm"
    MP4 = "mp4"


@dataclass
class TranscriptSegment:
    """Segmento de transcripcion con timestamps."""

    text: str
    start_time: float  # segundos
    end_time: float
    confidence: float = 1.0

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time

    def to_dict(self) -> Dict:
        return {
            "text": self.text,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "confidence": self.confidence,
        }


@dataclass
class Transcript:
    """Transcripcion completa de un archivo de audio/video."""

    source_file: str
    full_text: str
    segments: List[TranscriptSegment] = field(default_factory=list)
    language: str = "es"
    duration_seconds: float = 0.0
    transcribed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    model_used: str = "whisper-1"

    def to_dict(self) -> Dict:
        return {
            "source_file": self.source_file,
            "full_text": self.full_text,
            "segments": [s.to_dict() for s in self.segments],
            "language": self.language,
            "duration_seconds": self.duration_seconds,
            "transcribed_at": self.transcribed_at,
            "model_used": self.model_used,
        }

    def get_text_at_timestamp(self, timestamp: float) -> Optional[str]:
        """Obtiene el texto en un timestamp especifico."""
        for segment in self.segments:
            if segment.start_time <= timestamp <= segment.end_time:
                return segment.text
        return None


class Transcriber:
    """
    Servicio de transcripcion usando Whisper API.

    Uso:
        transcriber = Transcriber()
        transcript = await transcriber.transcribe_file("audio.mp3")
        # Access result: transcript.full_text
    """

    SUPPORTED_FORMATS = {"mp3", "wav", "m4a", "ogg", "webm", "mp4", "mov", "avi"}
    MAX_FILE_SIZE_MB = 25  # Limite de Whisper API

    def __init__(self, api_key: Optional[str] = None):
        """
        Inicializa el transcriber.

        Args:
            api_key: OpenAI API key. Si no se proporciona, usa OPENAI_API_KEY env var.
        """
        import os

        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            logger.warning("No OpenAI API key provided. Transcription will fail.")

    async def transcribe_file(
        self, file_path: str, language: str = "es", include_timestamps: bool = True
    ) -> Transcript:
        """
        Transcribe un archivo de audio/video.

        Args:
            file_path: Ruta al archivo
            language: Codigo de idioma (es, en, etc.)
            include_timestamps: Si incluir timestamps por segmento

        Returns:
            Transcript con el texto y metadatos
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"Archivo no encontrado: {file_path}")

        suffix = path.suffix.lower().lstrip(".")
        if suffix not in self.SUPPORTED_FORMATS:
            raise ValueError(
                f"Formato no soportado: {suffix}. Soportados: {self.SUPPORTED_FORMATS}"
            )

        # Verificar tamano
        size_mb = path.stat().st_size / (1024 * 1024)
        if size_mb > self.MAX_FILE_SIZE_MB:
            logger.warning(f"Archivo grande ({size_mb:.1f}MB). Puede requerir chunking.")

        # Transcribir con Whisper
        return await self._call_whisper_api(
            file_path=str(path), language=language, include_timestamps=include_timestamps
        )

    async def transcribe_url(
        self, url: str, language: str = "es", include_timestamps: bool = True
    ) -> Transcript:
        """
        Descarga y transcribe audio/video desde URL.

        Args:
            url: URL del archivo
            language: Codigo de idioma
            include_timestamps: Si incluir timestamps

        Returns:
            Transcript con el texto y metadatos
        """
        import httpx

        # Descargar a archivo temporal
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()

            # Determinar extension
            content_type = response.headers.get("content-type", "")
            ext = self._get_extension_from_content_type(content_type) or "mp3"

            with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
                tmp.write(response.content)
                tmp_path = tmp.name

        try:
            return await self.transcribe_file(tmp_path, language, include_timestamps)
        finally:
            # Limpiar archivo temporal
            Path(tmp_path).unlink(missing_ok=True)

    async def _call_whisper_api(
        self, file_path: str, language: str, include_timestamps: bool
    ) -> Transcript:
        """Llama a la API de Whisper."""
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=self.api_key)

            with open(file_path, "rb") as audio_file:
                # Usar verbose_json para obtener timestamps
                response_format = "verbose_json" if include_timestamps else "text"

                response = await client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language=language,
                    response_format=response_format,
                    prompt="Hola, ¿cómo estás? Bueno, te cuento que estuve en el evento. Me pareció genial, la verdad. Te mando un beso.",
                )

            # Parsear respuesta segun formato
            if include_timestamps and hasattr(response, "segments"):
                segments = [
                    TranscriptSegment(
                        text=getattr(seg, "text", "").strip(),
                        start_time=getattr(seg, "start", 0),
                        end_time=getattr(seg, "end", 0),
                        confidence=getattr(seg, "confidence", 1.0),
                    )
                    for seg in response.segments
                ]
                full_text = response.text
                duration = response.duration if hasattr(response, "duration") else 0
            else:
                full_text = response if isinstance(response, str) else response.text
                segments = []
                duration = 0

            return Transcript(
                source_file=file_path,
                full_text=full_text.strip(),
                segments=segments,
                language=language,
                duration_seconds=duration,
                model_used="whisper-1",
            )

        except ImportError:
            raise ImportError("openai package required. Install with: pip install openai")
        except Exception as e:
            logger.error(f"Error en transcripcion: {e}")
            raise

    def _get_extension_from_content_type(self, content_type: str) -> Optional[str]:
        """Mapea content-type a extension de archivo."""
        mapping = {
            "audio/mpeg": "mp3",
            "audio/mp3": "mp3",
            "audio/wav": "wav",
            "audio/x-wav": "wav",
            "audio/mp4": "m4a",
            "audio/m4a": "m4a",
            "audio/ogg": "ogg",
            "video/mp4": "mp4",
            "video/webm": "webm",
        }
        for key, ext in mapping.items():
            if key in content_type.lower():
                return ext
        return None


# Singleton
_transcriber: Optional[Transcriber] = None


def get_transcriber() -> Transcriber:
    """Obtiene instancia singleton del transcriber."""
    global _transcriber
    if _transcriber is None:
        _transcriber = Transcriber()
    return _transcriber
