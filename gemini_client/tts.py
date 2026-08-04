# -*- coding: utf-8 -*-
"""
gemini_client/tts.py
====================
Resilient async TTS pipeline with serialized playback and blocking-safe fallback.

Design decisions (per validation report)
-----------------------------------------
- Playback is serialized via asyncio.Lock — one utterance plays at a time,
  preventing audio overlap from rapid back-to-back sentences.
- asyncio.wait_for() (not asyncio.timeout()) is used for Python 3.10 compat.
- The Windows SAPI fallback runs inside asyncio.to_thread() so the blocking
  COM call does NOT block the event loop.
- MCI resources are explicitly closed in a finally block to prevent handle
  leaks even when playback is cancelled.
- The outer except catches only Exception, not BaseException, preserving
  KeyboardInterrupt and CancelledError propagation.
- Returns a SpeakResult dataclass so callers can log success/failure cleanly.

Usage::

    engine = TTSEngine(voice_name="en-US-AvaNeural")

    result = await engine.speak("Hello Joy!")
    if not result.success:
        print("TTS failed:", result.error)

    await engine.close()
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
import tempfile
import time
from dataclasses import dataclass, field
from typing import Optional


# ── Language detection ────────────────────────────────────────────────────────
_BANGLA_RANGE = re.compile(r'[\u0980-\u09ff]')


def _detect_voice(text: str, default_voice: str) -> str:
    """Return Bangla neural voice when Bangla characters detected, else default."""
    if _BANGLA_RANGE.search(text):
        return "bn-BD-NabanitaNeural"
    return default_voice


# ── Text cleaning (markdown → plain speech) ───────────────────────────────────
def _clean_for_tts(text: str) -> str:
    """Strip all markdown formatting symbols that would be read aloud by TTS."""
    # Remove fenced code blocks
    text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    text = re.sub(r'`[^`]*`', '', text)
    # Remove hyperlinks (keep link text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    # Remove bare URLs
    text = re.sub(r'https?://\S+', '', text)
    # Remove headings markers
    text = re.sub(r'#+\s*', '', text)
    # Remove horizontal rules
    text = re.sub(r'^[*\-_]{3,}\s*$', '', text, flags=re.MULTILINE)
    # Remove bold/italic markers (*text*, **text**, _text_, __text__)
    text = re.sub(r'[*_]+', '', text)
    # Remove bullet list markers
    text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
    # Remove ordered list markers
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
    # Final sweep: remove any remaining literal *, ~, ^, #
    text = text.replace('*', '').replace('~', '').replace('^', '').replace('#', '')
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# ── Result type ───────────────────────────────────────────────────────────────
@dataclass
class SpeakResult:
    success: bool
    method: str = ""       # "edge-tts-mci" | "edge-tts-file" | "sapi" | "skipped"
    error: Optional[str] = None
    duration_ms: float = 0.0


# ── Engine ────────────────────────────────────────────────────────────────────
class TTSEngine:
    """
    Async TTS engine with language auto-detection, MCI playback, and SAPI fallback.

    Parameters
    ----------
    voice_name : str
        Default edge-tts voice.  Bangla text automatically switches to
        'bn-BD-NabanitaNeural'.
    timeout_seconds : float
        Maximum time to wait for edge-tts synthesis and playback.  Default 10s.
    """

    def __init__(
        self,
        voice_name: str = "en-US-AvaNeural",
        timeout_seconds: float = 10.0,
    ) -> None:
        self.voice_name = voice_name
        self.timeout_seconds = timeout_seconds
        self._lock = asyncio.Lock()
        self._mci_counter = 0

    # ── Public API ────────────────────────────────────────────────────────────

    async def speak(self, text: str) -> SpeakResult:
        """
        Synthesize and play text.  Serialized — one utterance at a time.

        Skips empty text.  Cleans markdown before synthesis.
        Tries edge-tts + Windows MCI first; falls back to Windows SAPI.
        """
        clean = _clean_for_tts(text)
        if not clean:
            return SpeakResult(success=True, method="skipped")

        voice = _detect_voice(clean, self.voice_name)

        async with self._lock:
            t0 = time.monotonic()
            result = await self._try_edge_tts_mci(clean, voice)
            if not result.success:
                result = await self._try_sapi_fallback(clean)
            result.duration_ms = (time.monotonic() - t0) * 1000
            return result

    async def synthesize_bytes(self, text: str) -> Optional[bytes]:
        """Synthesizes text directly to audio bytes (MP3 format)."""
        clean = _clean_for_tts(text)
        if not clean:
            return None
        voice = _detect_voice(clean, self.voice_name)
        try:
            import edge_tts
            communicate = edge_tts.Communicate(clean, voice)
            audio_chunks = []
            async for chunk in communicate.stream():
                if chunk.get("type") == "audio" and chunk.get("data"):
                    audio_chunks.append(chunk["data"])
            if audio_chunks:
                return b"".join(audio_chunks)
        except Exception as e:
            console.log(f"[yellow]edge-tts stream error: {e}[/yellow]")
        return None

    async def close(self) -> None:
        """No-op — kept for API symmetry."""

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _try_edge_tts_mci(self, text: str, voice: str) -> SpeakResult:
        """Synthesize via edge-tts, play via Windows MCI (mciSendStringW)."""
        if sys.platform != "win32":
            return SpeakResult(success=False, method="edge-tts-mci", error="Not Windows")

        try:
            import edge_tts  # type: ignore
        except ImportError:
            return SpeakResult(success=False, method="edge-tts-mci", error="edge-tts not installed")

        tmp_path: Optional[str] = None
        alias: Optional[str] = None
        try:
            async def _synthesize_and_play() -> None:
                nonlocal tmp_path, alias
                import ctypes
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                    tmp_path = f.name

                communicate = edge_tts.Communicate(text, voice)
                await communicate.save(tmp_path)

                if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) == 0:
                    raise RuntimeError("edge-tts produced an empty MP3 file")

                self._mci_counter += 1
                alias = f"gemtts_{self._mci_counter}"
                winmm = ctypes.windll.winmm
                winmm.mciSendStringW(f'open "{tmp_path}" type mpegvideo alias {alias}', None, 0, 0)
                winmm.mciSendStringW(f'play {alias} wait', None, 0, 0)

            await asyncio.wait_for(_synthesize_and_play(), timeout=self.timeout_seconds)
            return SpeakResult(success=True, method="edge-tts-mci")

        except asyncio.TimeoutError:
            return SpeakResult(success=False, method="edge-tts-mci", error="Timed out")
        except Exception as exc:
            return SpeakResult(success=False, method="edge-tts-mci", error=str(exc))
        finally:
            # Always release MCI handle and delete temp file
            if alias is not None:
                try:
                    import ctypes
                    ctypes.windll.winmm.mciSendStringW(f'close {alias}', None, 0, 0)
                except Exception:
                    pass
            if tmp_path is not None:
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    async def _try_sapi_fallback(self, text: str) -> SpeakResult:
        """Blocking SAPI fallback, offloaded to a thread so the event loop is not blocked."""
        if sys.platform != "win32":
            return SpeakResult(success=False, method="sapi", error="Not Windows")

        def _sapi_speak() -> None:
            import win32com.client  # type: ignore
            speaker = win32com.client.Dispatch("SAPI.SpVoice")
            speaker.Speak(text)

        try:
            await asyncio.wait_for(
                asyncio.to_thread(_sapi_speak),
                timeout=self.timeout_seconds,
            )
            return SpeakResult(success=True, method="sapi")
        except asyncio.TimeoutError:
            return SpeakResult(success=False, method="sapi", error="SAPI timed out")
        except Exception as exc:
            return SpeakResult(success=False, method="sapi", error=str(exc))
