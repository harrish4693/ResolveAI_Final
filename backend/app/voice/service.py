import os
import uuid
import mimetypes
from pathlib import Path
from fastapi import UploadFile, HTTPException

from app.voice.providers import StubSTTProvider, StubTTSProvider, STTProvider, TTSProvider
from app.config import settings

# In a real application, we would initialize these from config
stt_provider: STTProvider = StubSTTProvider()
tts_provider: TTSProvider = StubTTSProvider()


class VoiceService:
    """Service for handling audio file storage, validation, and STT/TTS integration."""
    
    # Use a directory inside the backend workspace for storage
    BASE_AUDIO_DIR = Path("data/audio/conversations").resolve()
    
    ALLOWED_MIME_TYPES = {
        "audio/webm",
        "audio/mp3",
        "audio/mpeg",
        "audio/wav",
        "audio/ogg",
        "video/webm", # Some browsers send audio/webm as video/webm
    }
    
    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB limit

    @classmethod
    def _ensure_dir(cls, conversation_id: int) -> Path:
        """Ensures the directory for a conversation exists and returns it."""
        dir_path = cls.BASE_AUDIO_DIR / str(conversation_id)
        # Prevent path traversal
        try:
            dir_path.resolve().relative_to(cls.BASE_AUDIO_DIR)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid conversation ID")
            
        os.makedirs(dir_path, exist_ok=True)
        return dir_path

    @classmethod
    async def save_customer_audio(cls, conversation_id: int, file: UploadFile) -> str:
        """
        Validates and saves the customer's uploaded audio file.
        Returns the application-relative URL for the audio.
        """
        if not file.content_type in cls.ALLOWED_MIME_TYPES:
            raise HTTPException(
                status_code=400, 
                detail=f"Unsupported audio format: {file.content_type}. Allowed: {', '.join(cls.ALLOWED_MIME_TYPES)}"
            )

        # File size check
        file.file.seek(0, os.SEEK_END)
        size = file.file.tell()
        file.file.seek(0)
        
        if size == 0:
            raise HTTPException(status_code=400, detail="Empty audio file")
        if size > cls.MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail="Audio file too large (max 5MB)")

        # Generate a safe filename
        ext = mimetypes.guess_extension(file.content_type) or ".webm"
        if ext == ".jpe": # Sometimes mimetypes guesses wrong for webm depending on OS
            ext = ".webm"
        
        filename = f"msg_{uuid.uuid4().hex[:8]}_input{ext}"
        dir_path = cls._ensure_dir(conversation_id)
        file_path = dir_path / filename

        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)

        # Return the relative URL string that the API will serve
        return f"/api/audio/conversations/{conversation_id}/{filename}"

    @classmethod
    def get_absolute_path(cls, audio_url: str) -> Path:
        """Converts an audio URL into an absolute file path and validates it."""
        prefix = "/api/audio/conversations/"
        if not audio_url.startswith(prefix):
            raise ValueError("Invalid audio URL format")
            
        rel_path = audio_url[len(prefix):]
        parts = rel_path.split("/")
        if len(parts) != 2:
            raise ValueError("Invalid audio URL path segments")
            
        conversation_id, filename = parts
        
        # Prevent path traversal
        if ".." in conversation_id or ".." in filename or "/" in filename:
            raise ValueError("Path traversal detected")
            
        target_path = (cls.BASE_AUDIO_DIR / conversation_id / filename).resolve()
        
        try:
            target_path.relative_to(cls.BASE_AUDIO_DIR)
        except ValueError:
            raise ValueError("Path traversal detected")
            
        return target_path

    @classmethod
    async def transcribe(cls, audio_url: str) -> str:
        """Transcribes the given audio URL to text using the configured STT provider."""
        try:
            file_path = cls.get_absolute_path(audio_url)
            from app.voice.providers import get_stt_provider
            provider = get_stt_provider()
            return await provider.transcribe(str(file_path))
        except Exception as e:
            # We wrap it in a specific exception if we want to handle it higher up
            raise RuntimeError(f"STT failed: {str(e)}")

    @classmethod
    async def synthesize_ai_response(cls, conversation_id: int, text: str) -> str:
        """
        Synthesizes AI text response to audio using the TTS provider.
        Returns the application-relative URL for the generated audio.
        """
        dir_path = cls._ensure_dir(conversation_id)
        filename = f"msg_{uuid.uuid4().hex[:8]}_response.mp3"
        file_path = dir_path / filename

        try:
            await tts_provider.synthesize(text, str(file_path))
            return f"/api/audio/conversations/{conversation_id}/{filename}"
        except Exception as e:
            raise RuntimeError(f"TTS failed: {str(e)}")
