"""
ResolveAIV2 — Streaming Voice Provider Interfaces & Mocks (M12.7)

These interfaces define the contract for real-time streaming
Speech-to-Text and Text-to-Speech providers.

They are intentionally separate from the existing file-based
STTProvider / TTSProvider which remain used for non-streaming
voice messages (M5).

Mock implementations return deterministic results for CI testing.
They do NOT pretend to be real streaming engines.
"""

import asyncio
import uuid
from abc import ABC, abstractmethod
from typing import AsyncIterator


# ═══════════════════════════════════════════════════════════
# Streaming STT
# ═══════════════════════════════════════════════════════════


class StreamingSTTProvider(ABC):
    """Abstract interface for streaming Speech-to-Text.

    Implementations receive audio chunks incrementally and yield
    partial transcripts, culminating in a final transcript.
    """

    @abstractmethod
    async def start_session(self) -> str:
        """Start a new STT session. Returns a session_id."""
        pass

    @abstractmethod
    async def feed_audio(self, session_id: str, audio_chunk: bytes) -> str | None:
        """Feed an audio chunk to the session.

        Returns a partial transcript string if available, or None.
        """
        pass

    @abstractmethod
    async def finalize(self, session_id: str) -> str:
        """Finalize the session and return the complete transcript.

        After this call the session is closed and no more audio
        can be fed.
        """
        pass

    @abstractmethod
    async def cancel(self, session_id: str) -> None:
        """Cancel an active session and release resources."""
        pass


class MockStreamingSTTProvider(StreamingSTTProvider):
    """Deterministic mock for CI and local testing.

    Behaviour:
    - Buffers all audio chunks as raw bytes.
    - On finalize, if the buffered bytes decode to readable UTF-8 text,
      returns that text (allows test fixtures to embed expected output).
    - Otherwise returns a fixed deterministic string.
    - Does NOT simulate latency — tests should be fast.
    """

    def __init__(self):
        self._sessions: dict[str, bytearray] = {}

    async def start_session(self) -> str:
        session_id = f"mock-stt-{uuid.uuid4().hex[:8]}"
        self._sessions[session_id] = bytearray()
        return session_id

    async def feed_audio(self, session_id: str, audio_chunk: bytes) -> str | None:
        if session_id not in self._sessions:
            raise ValueError(f"Unknown STT session: {session_id}")
        self._sessions[session_id].extend(audio_chunk)
        # Mock: no partial transcripts
        return None

    async def finalize(self, session_id: str) -> str:
        if session_id not in self._sessions:
            raise ValueError(f"Unknown STT session: {session_id}")

        raw = bytes(self._sessions.pop(session_id))

        # Allow test fixtures to embed expected transcript text
        try:
            decoded = raw.decode("utf-8", errors="strict").strip()
            if decoded:
                return decoded
        except UnicodeDecodeError:
            pass

        return "This is a mock voice transcription."

    async def cancel(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)


# ═══════════════════════════════════════════════════════════
# Streaming TTS
# ═══════════════════════════════════════════════════════════


class StreamingTTSProvider(ABC):
    """Abstract interface for streaming Text-to-Speech.

    Implementations accept validated text and yield audio chunks
    that can be streamed over WebSocket in real time.
    """

    @abstractmethod
    async def synthesize_stream(self, text: str) -> AsyncIterator[bytes]:
        """Yield audio chunks for the given text.

        The caller is responsible for sending each chunk to the client.
        If cancelled (e.g. via barge-in), the caller simply stops
        iterating and discards remaining chunks.
        """
        pass  # pragma: no cover


class MockStreamingTTSProvider(StreamingTTSProvider):
    """Deterministic mock for CI and local testing.

    Behaviour:
    - Splits the input text into 3 fixed-size chunks.
    - Each chunk is prefixed with a marker for easy assertion.
    - If text contains 'fail_tts', raises immediately.
    - Does NOT simulate latency.
    """

    # Track calls for test assertions
    call_count: int = 0
    last_text: str | None = None

    async def synthesize_stream(self, text: str) -> AsyncIterator[bytes]:
        if "fail_tts" in text.lower():
            raise ValueError("Simulated streaming TTS failure")

        MockStreamingTTSProvider.call_count += 1
        MockStreamingTTSProvider.last_text = text

        # Produce 3 deterministic chunks
        encoded = text.encode("utf-8")
        chunk_size = max(1, len(encoded) // 3)

        for i in range(0, len(encoded), chunk_size):
            chunk = encoded[i : i + chunk_size]
            yield b"MOCK_AUDIO_CHUNK:" + chunk

    @classmethod
    def reset(cls):
        """Reset tracking state between tests."""
        cls.call_count = 0
        cls.last_text = None
