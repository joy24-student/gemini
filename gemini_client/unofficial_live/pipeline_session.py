from __future__ import annotations

import asyncio
import queue
import re
import sys
import threading
import time
from typing import AsyncIterator, Callable, Optional

from rich.console import Console

from gemini_client.tts import TTSEngine

console = Console()

# Sentence demarcation regex pattern for sentence-level audio pipelining
_SENTENCE_PATTERN = re.compile(r'([^.!?\n]+[.!?\n]+)')


class UnofficialSpeakerStream:
    """Non-blocking audio playback worker using PyAudio or sounddevice."""

    def __init__(self, sample_rate: int = 24000):
        self.sample_rate = sample_rate
        self.queue: queue.Queue[bytes] = queue.Queue()
        self.running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        """Start the background audio playback thread."""
        self.running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def play_pcm(self, pcm_data: bytes):
        """Enqueue PCM bytes for immediate streaming playback."""
        self.queue.put(pcm_data)

    def clear(self):
        """Clear all queued audio chunks (used on user interruption / barge-in)."""
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except queue.Empty:
                break

    def stop(self):
        self.running = False
        self.clear()

    def _run(self):
        try:
            import pyaudio
            pa = pyaudio.PyAudio()
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.sample_rate,
                output=True,
                frames_per_buffer=1024,
            )
            while self.running:
                try:
                    chunk = self.queue.get(timeout=0.1)
                    stream.write(chunk)
                except queue.Empty:
                    continue
            stream.stop_stream()
            stream.close()
            pa.terminate()
        except ImportError:
            # Fallback if pyaudio is not installed
            pass


# _clean_markdown_text and _detect_voice are now provided by gemini_client.tts
# kept here for any external importers
def _clean_markdown_text(text: str) -> str:
    """Strip all markdown formatting syntax before passing to TTS synthesizer."""
    from gemini_client.tts import _clean_for_tts
    return _clean_for_tts(text)

def _detect_voice(text: str, default_voice: str) -> str:
    """Detect language and select matching TTS voice."""
    from gemini_client.tts import _detect_voice as _tv
    return _tv(text, default_voice)

class PipelineLiveSession:
    """
    Real-Time Unofficial Live Streaming Pipeline.

    Integrates with AsyncChatbot.ask_stream() for sub-200ms real-time voice & text output.
    Uses TTSEngine from gemini_client.tts for resilient audio playback.
    """

    def __init__(
        self,
        chatbot,
        voice_name: str = "en-US-AvaNeural",
        on_text_chunk: Optional[Callable[[str], None]] = None,
        on_sentence: Optional[Callable[[str], None]] = None,
    ):
        self.chatbot = chatbot
        self.voice_name = voice_name
        self.on_text_chunk = on_text_chunk
        self.on_sentence = on_sentence
        self.speaker = UnofficialSpeakerStream()
        self._is_active = False
        # TTSEngine owns the playback lock — one utterance at a time
        self._tts = TTSEngine(voice_name=voice_name, timeout_seconds=10.0)

    async def send_voice_prompt(self, user_prompt: str) -> str:
        """
        Stream a user message to Gemini Web UI, pipelining text tokens to terminal
        and synthesizing sentence-level audio concurrently.
        """
        self.speaker.clear()
        if not self.speaker.running:
            self.speaker.start()

        full_text = []
        buffer = ""

        console.log(f"\n[bold green]🧑 You:[/bold green] {user_prompt}")
        console.print("[bold cyan]🤖 Gemini (Live Streaming):[/bold cyan] ", end="")

        async for chunk in self.chatbot.ask_stream(user_prompt):
            full_text.append(chunk)
            buffer += chunk

            if self.on_text_chunk:
                self.on_text_chunk(chunk)
            else:
                print(chunk, end="", flush=True)

            # Check if we have complete sentences in the buffer
            matches = list(_SENTENCE_PATTERN.finditer(buffer))
            if matches:
                last_end = 0
                for match in matches:
                    sentence = match.group(1).strip()
                    if sentence:
                        if self.on_sentence:
                            self.on_sentence(sentence)
                        # Pipeline synthesis asynchronously via TTSEngine
                        asyncio.create_task(self._synthesize_and_play(sentence))
                    last_end = match.end()
                buffer = buffer[last_end:]

        # Process any remaining text in buffer after stream completes
        if buffer.strip():
            if self.on_sentence:
                self.on_sentence(buffer.strip())
            asyncio.create_task(self._synthesize_and_play(buffer.strip()))

        print()  # newline
        return "".join(full_text)

    async def _synthesize_and_play(self, text: str):
        """
        Synthesize text to speech via TTSEngine.
        TTSEngine handles: lock serialization, MCI playback, timeout,
        SAPI fallback via asyncio.to_thread, and MCI resource cleanup.
        """
        result = await self._tts.speak(text)
        if not result.success and result.method != "skipped":
            console.log(f"[yellow]⚠️  TTS failed ({result.method}): {result.error}[/yellow]")









