"""
Audio Router - Whisper transcription endpoint for the inbox.

Endpoints:
- POST /audio/transcribe - Transcribe uploaded audio file to text
"""

import logging
import os
import tempfile

from fastapi import APIRouter, File, HTTPException, UploadFile

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/audio", tags=["audio"])

# Max file size: 25MB (Whisper API limit)
MAX_FILE_SIZE = 25 * 1024 * 1024
# Min file size: 1KB (skip empty/corrupt files)
MIN_FILE_SIZE = 1000


@router.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...), language: str = "es"):
    """
    Transcribe an uploaded audio file using Whisper API.

    Accepts audio files (webm, mp3, wav, m4a, ogg, mp4) up to 25MB.
    Returns the transcribed text.
    """
    from ingestion.transcriber import get_transcriber

    # Determine file extension
    suffix = os.path.splitext(file.filename or ".webm")[1] or ".webm"

    # Read file content
    content = await file.read()

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large. Max 25MB.")

    if len(content) < MIN_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Audio too short or empty.")

    # Write to temp file for Whisper API
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        transcriber = get_transcriber()
        transcript = await transcriber.transcribe_file(tmp_path, language=language)
        return {"text": transcript.full_text.strip(), "language": language}
    except Exception as e:
        logger.error(f"[Audio] Transcription failed: {e}")
        raise HTTPException(status_code=500, detail=f"Transcription failed: {e}")
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
