"""
Transcriber - 2-Tier Cascade: Groq → Gemini.

Tier 0 (FREE):    Groq Whisper v3 Turbo (2000 req/day, 8h audio/day)
Tier 1 ($0.0006): Gemini 2.0 Flash audio native (httpx REST)

Supports:
- Local audio/video files (mp3, wav, m4a, ogg, webm, mp4)
- URLs (auto-download + cascade)

Dependencies:
- openai (Groq via OpenAI-compatible client)
- httpx (Gemini REST + URL downloads)
"""

import base64
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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
    language: str = "auto"
    duration_seconds: float = 0.0
    transcribed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    model_used: str = "unknown"

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
    2-Tier cascade transcription service.

    Tier 0: Groq Whisper v3 Turbo (free, 2000 req/day)
    Tier 1: Gemini 2.0 Flash audio native (~$0.0006/min)

    Usage:
        transcriber = Transcriber()
        transcript = await transcriber.transcribe_file("audio.mp3")
    """

    SUPPORTED_FORMATS = {"mp3", "wav", "m4a", "ogg", "webm", "mp4", "mov", "avi"}
    MAX_FILE_SIZE_MB = 25  # Whisper API limit

    EXT_TO_MIME = {
        "ogg": "audio/ogg",
        "mp3": "audio/mpeg",
        "m4a": "audio/mp4",
        "wav": "audio/wav",
        "webm": "audio/webm",
        "mp4": "video/mp4",
        "mov": "video/quicktime",
        "avi": "video/x-msvideo",
    }

    def __init__(self):
        self.groq_api_key = os.getenv("GROQ_API_KEY")
        self.google_api_key = os.getenv("GOOGLE_API_KEY")

    async def transcribe_file(
        self, file_path: str, language: Optional[str] = None, include_timestamps: bool = True
    ) -> Transcript:
        """Transcribe a local audio/video file using the 3-tier cascade."""
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"Archivo no encontrado: {file_path}")

        suffix = path.suffix.lower().lstrip(".")
        if suffix not in self.SUPPORTED_FORMATS:
            raise ValueError(
                f"Formato no soportado: {suffix}. Soportados: {self.SUPPORTED_FORMATS}"
            )

        size_mb = path.stat().st_size / (1024 * 1024)
        if size_mb > self.MAX_FILE_SIZE_MB:
            logger.warning(f"Archivo grande ({size_mb:.1f}MB). Puede requerir chunking.")

        audio_bytes = path.read_bytes()
        mime_type = self.EXT_TO_MIME.get(suffix, "audio/ogg")

        text, model_used, detected_lang = await self._transcribe_cascade(audio_bytes, mime_type, language)

        return Transcript(
            source_file=str(path),
            full_text=text,
            segments=[],
            language=detected_lang or "auto",
            duration_seconds=0,
            model_used=model_used,
        )

    async def transcribe_url(
        self, url: str, language: Optional[str] = None, include_timestamps: bool = True
    ) -> Transcript:
        """Download and transcribe audio/video from URL using the 3-tier cascade."""
        import httpx

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()

            content_type = response.headers.get("content-type", "")
            ext = self._get_extension_from_content_type(content_type) or "mp3"
            mime_type = self.EXT_TO_MIME.get(ext, "audio/ogg")
            audio_bytes = response.content

        text, model_used, detected_lang = await self._transcribe_cascade(audio_bytes, mime_type, language)

        return Transcript(
            source_file=url,
            full_text=text,
            segments=[],
            language=detected_lang or "auto",
            duration_seconds=0,
            model_used=model_used,
        )

    # ── Cascade orchestrator ──────────────────────────────────────────

    async def _transcribe_cascade(
        self, audio_bytes: bytes, mime_type: str, language: Optional[str]
    ) -> Tuple[str, str, Optional[str]]:
        """Try Tier 0 → Tier 1. Returns (text, model_name, detected_lang).

        language=None means auto-detect (multilingual). Pass an ISO code like
        "es" or "ca" only to force a specific language.
        """

        # TIER 0: Groq Whisper v3 Turbo (free)
        if self.groq_api_key:
            try:
                t0 = time.monotonic()
                text, detected = await self._transcribe_groq(audio_bytes, mime_type, language)
                elapsed = time.monotonic() - t0
                logger.info(
                    f"[AUDIO_CASCADE] TIER 0 Groq free OK ({len(text)} chars, {elapsed:.1f}s"
                    f"{f', lang={detected}' if detected else ''})"
                )
                return text, "groq-whisper-v3-turbo", detected
            except Exception as e:
                logger.warning(f"[AUDIO_CASCADE] TIER 0 Groq failed ({e}) → escalating")
        else:
            logger.debug("[AUDIO_CASCADE] TIER 0 Groq skipped (no GROQ_API_KEY)")

        # TIER 1: Gemini 2.0 Flash audio native
        if self.google_api_key:
            try:
                t0 = time.monotonic()
                text = await self._transcribe_gemini_audio(audio_bytes, mime_type, language)
                elapsed = time.monotonic() - t0
                logger.info(
                    f"[AUDIO_CASCADE] TIER 1 Gemini audio OK ({len(text)} chars, {elapsed:.1f}s)"
                )
                return text, "gemini-2.0-flash-audio", language
            except Exception as e:
                logger.warning(f"[AUDIO_CASCADE] TIER 1 Gemini failed ({e}) → giving up")
        else:
            logger.debug("[AUDIO_CASCADE] TIER 1 Gemini skipped (no GOOGLE_API_KEY)")

        logger.error("[AUDIO_CASCADE] All tiers failed, returning empty transcript")
        return "", "none", language

    # ── Tier 0: Groq ─────────────────────────────────────────────────

    async def _transcribe_groq(
        self, audio_bytes: bytes, mime_type: str, language: Optional[str]
    ) -> Tuple[str, Optional[str]]:
        """Groq Whisper v3 Turbo via OpenAI-compatible API.

        When language=None, omits the language param so Whisper auto-detects.
        Whisper supports Catalan ("ca") and Spanish ("es") natively.
        Returns (text, detected_language).
        """
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=self.groq_api_key,
            base_url="https://api.groq.com/openai/v1",
        )

        kwargs: Dict = {
            "model": "whisper-large-v3-turbo",
            "file": ("audio.ogg", audio_bytes, mime_type),
            "response_format": "verbose_json",  # needed to read detected language
        }
        if language:
            kwargs["language"] = language

        response = await client.audio.transcriptions.create(**kwargs)

        text = response.text if hasattr(response, "text") else str(response)
        detected = getattr(response, "language", None) or language
        return text.strip(), detected

    # ── Tier 1: Gemini 2.0 Flash audio native ────────────────────────

    async def _transcribe_gemini_audio(
        self, audio_bytes: bytes, mime_type: str, language: Optional[str]
    ) -> str:
        """Gemini 2.0 Flash with inline audio data (REST, no SDK)."""
        import httpx

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.0-flash:generateContent?key={self.google_api_key}"
        )

        if language:
            lang_name = "español" if language == "es" else "inglés" if language == "en" else language
            prompt = (
                f"Transcribe este audio palabra por palabra en {lang_name}. "
                f"Devuelve SOLO la transcripción literal, nada más."
            )
        else:
            prompt = (
                "Transcribe this audio word for word in the exact language spoken. "
                "Do NOT translate. Return ONLY the literal transcription, nothing else."
            )

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": base64.b64encode(audio_bytes).decode(),
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 4096},
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()

        data = resp.json()
        candidates = data.get("candidates", [])
        if not candidates:
            raise ValueError("Gemini returned no candidates")

        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            raise ValueError("Gemini returned no parts")

        return parts[0].get("text", "").strip()

    # ── Helpers ────────────────────────────────────────────────────────

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
