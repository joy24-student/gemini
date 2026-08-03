# -*- coding: utf-8 -*-
"""
gemini_client.unofficial_live
=============================
Advanced Unofficial Real-Time Live Streaming & Playwright Conversation Engine.
100% Unofficial — ZERO Official API Keys Required.

Supports:
  - Ultra-Low Latency Text + Voice Pipeline Engine (pipeline_session.py)
  - Playwright Headless Chromium Real-Time Process Engine (playwright_session.py)
  - Sentence-boundary token buffering & concurrent TTS synthesis
"""
import asyncio
from typing import Optional

from rich.console import Console

from .pipeline_session import PipelineLiveSession, UnofficialSpeakerStream
from .playwright_session import PlaywrightLiveSession
from .websocket_live import UnofficialLiveWebSocket, UnofficialLiveBridgeServer
from .official_adapter import (
    build_server_content,
    build_setup_complete,
    parse_client_message,
)
from gemini_client.core import Chatbot, AsyncChatbot, Model

console = Console()


class UnofficialLiveChatbot:
    """
    High-level entry point for Unofficial Real-Time Live Conversation.

    Parameters
    ----------
    cookie_path : str, optional
        Path to cookies.json.
    auto_cookie : bool
        If True, automatically extracts browser cookies. Default False.
    model : Model
        Gemini model variant to use.
    """

    def __init__(
        self,
        cookie_path: Optional[str] = None,
        auto_cookie: bool = False,
        model: Model = Model.G_2_5_FLASH,
        secure_1psid: Optional[str] = None,
        secure_1psidts: Optional[str] = None,
    ):
        self.cookie_path = cookie_path
        self.auto_cookie = auto_cookie
        self.model = model
        self.secure_1psid = secure_1psid
        self.secure_1psidts = secure_1psidts
        self.bot = None
        self.pipeline = None
        self.ws = None

    async def initialize(self):
        """Asynchronously initialize the underlying HTTP/2 session and live engines."""
        if not self.bot:
            import os
            if self.secure_1psid and self.secure_1psidts:
                psid, psidts = self.secure_1psid, self.secure_1psidts
            elif self.cookie_path and os.path.exists(self.cookie_path):
                from gemini_client.utils import load_cookies
                psid, psidts = load_cookies(self.cookie_path)
            elif self.auto_cookie:
                from gemini_client.cookie_manager import CookieExtractor
                extractor = CookieExtractor()
                cookies = extractor.extract_cookies(save_to_disk=False)
                psid, psidts = cookies['__Secure-1PSID'], cookies['__Secure-1PSIDTS']
            else:
                psid, psidts = "", ""

            async_bot = await AsyncChatbot.create(secure_1psid=psid, secure_1psidts=psidts, model=self.model)
            self.bot = async_bot
            self.pipeline = PipelineLiveSession(async_bot)
            self.ws = UnofficialLiveWebSocket(async_bot)

    async def __aenter__(self):
        await self.initialize()
        return self

    async def __aexit__(self, *args):
        if self.pipeline and hasattr(self.pipeline, "speaker"):
            self.pipeline.speaker.stop()

    async def start_voice_pipeline(self) -> None:
        """
        Start a real-time live streaming voice conversation in the terminal.
        Reads user prompts and streams response text + voice concurrently (<200ms latency).
        """
        console.log("\n[bold green]🎙️  Unofficial Live Voice Pipeline Started![/bold green]")
        console.log("📝  Type your prompt and press Enter (type 'exit' to quit).\n")

        loop = asyncio.get_running_loop()
        while True:
            try:
                prompt = await loop.run_in_executor(None, input, "🧑 You: ")
                if prompt.strip().lower() in ("exit", "quit", "bye"):
                    break
                if not prompt.strip():
                    continue
                await self.pipeline.send_voice_prompt(prompt)
            except (KeyboardInterrupt, EOFError):
                break

        console.log("\n[yellow]Live session ended.[/yellow]")


__all__ = [
    "UnofficialLiveChatbot",
    "PipelineLiveSession",
    "PlaywrightLiveSession",
    "UnofficialSpeakerStream",
    # Official Protocol WebSocket Engine & Server
    "UnofficialLiveWebSocket",
    "UnofficialLiveBridgeServer",
    "build_server_content",
    "build_setup_complete",
    "parse_client_message",
]
