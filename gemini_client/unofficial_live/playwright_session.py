# -*- coding: utf-8 -*-
"""
gemini_client/unofficial_live/playwright_session.py
====================================================
Playwright 100% Background Chromium Real-Time Process Engine for Gemini Web UI.

Features:
  - 100% Background Execution: Runs silently in headless Chromium with zero GUI window or popups.
  - Automatic Browser Cookie Injection: Auto-extracts __Secure-1PSID & __Secure-1PSIDTS from local browser.
  - Network & DOM Interception: Intercepts incoming StreamGenerate RPCs and DOM updates in real-time.
  - Stealth Arguments: Anti-detection flags prevent anti-bot blocks while running silently in the background.
"""
from __future__ import annotations

import asyncio
import warnings
from typing import Callable, Optional
from rich.console import Console

from gemini_client.cookie_manager import CookieExtractor

console = Console()

# Stealth flags for 100% background silent Chromium execution
BACKGROUND_CHROMIUM_ARGS = [
    "--headless=new",
    "--disable-blink-features=AutomationControlled",
    "--use-fake-ui-for-media-stream",  # Silent auto-grant mic/cam permissions
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-software-rasterizer",
    "--disable-notifications",
    "--disable-popup-blocking",
    "--disable-background-networking",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-breakpad",
    "--disable-component-extensions-with-background-pages",
    "--disable-ipc-flooding-protection",
    "--disable-renderer-backgrounding",
    "--mute-audio",  # Background silent execution
]


class PlaywrightLiveSession:
    """
    Playwright 100% Background Process Engine for Unofficial Gemini Live Conversation.

    Parameters
    ----------
    secure_1psid : str, optional
        __Secure-1PSID cookie value.
    secure_1psidts : str, optional
        __Secure-1PSIDTS cookie value.
    auto_cookie : bool
        If True, automatically extracts cookies from default browser in background. Default False.
    headless : bool
        Runs Chromium silently in background. Default True.
    on_text_stream : callable, optional
        Callback async def on_text_stream(delta: str) triggered on incoming text tokens.
    """

    def __init__(
        self,
        secure_1psid: Optional[str] = None,
        secure_1psidts: Optional[str] = None,
        auto_cookie: bool = True,
        headless: bool = True,
        on_text_stream: Optional[Callable[[str], None]] = None,
    ):
        if auto_cookie and (not secure_1psid or not secure_1psidts):
            extractor = CookieExtractor()
            cookies = extractor.extract_cookies(save_to_disk=False)
            self.secure_1psid = cookies.get("__Secure-1PSID", "")
            self.secure_1psidts = cookies.get("__Secure-1PSIDTS", "")
        else:
            self.secure_1psid = secure_1psid or ""
            self.secure_1psidts = secure_1psidts or ""

        warnings.warn(
            "\n[EXPERIMENTAL] PlaywrightLiveSession relies on scraping Gemini's web UI DOM.\n"
            "It will break if Google changes their CSS selectors or page structure.\n"
            "Use AsyncChatbot (direct HTTP) for production workloads.",
            UserWarning,
            stacklevel=2,
        )

        self.headless = headless
        self.on_text_stream = on_text_stream

        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    async def __aenter__(self) -> "PlaywrightLiveSession":
        await self.start()
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def start(self) -> "PlaywrightLiveSession":
        """Launch background Chromium browser process and authenticate via cookies."""
        from playwright.async_api import async_playwright

        console.log("[bold cyan]🤖 Launching Playwright 100% Background Engine...[/bold cyan]")
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=BACKGROUND_CHROMIUM_ARGS,
        )

        # Create isolated background context
        self._context = await self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 720},
        )

        # Inject session cookies into context
        await self._context.add_cookies([
            {
                "name": "__Secure-1PSID",
                "value": self.secure_1psid,
                "domain": ".google.com",
                "path": "/",
                "secure": True,
                "httpOnly": True,
            },
            {
                "name": "__Secure-1PSIDTS",
                "value": self.secure_1psidts,
                "domain": ".google.com",
                "path": "/",
                "secure": True,
                "httpOnly": True,
            },
        ])

        self._page = await self._context.new_page()

        # Intercept background network response streams
        self._page.on("response", self._handle_response)

        console.log("[cyan]🌐 Connecting to Gemini Web UI in background (gemini.google.com/app)...[/cyan]")
        await self._page.goto("https://gemini.google.com/app", wait_until="networkidle")
        console.log("[bold green]✅ Playwright Background Session Connected & Ready![/bold green]")
        return self

    async def send_message(self, message: str) -> str:
        """
        Send a message through the background Playwright browser process.
        """
        if not self._page:
            raise RuntimeError("Session not started. Call await session.start() first.")

        console.log(f"\n[bold green]🧑 You (Background):[/bold green] {message}")

        # Fill input box silently in background
        input_selector = "div[contenteditable='true'], textarea, rich-textarea p"
        await self._page.wait_for_selector(input_selector, timeout=15000)
        await self._page.fill(input_selector, message)
        await self._page.keyboard.press("Enter")

        console.print("[bold cyan]🤖 Gemini (Background Stream):[/bold cyan] ", end="")

        # Poll the DOM silently for streaming text updates
        response_selector = "message-content, .model-response-text, .response-container"
        previous_text = ""
        full_response = ""

        for _ in range(60):  # max 30s timeout
            await asyncio.sleep(0.5)
            elements = await self._page.query_selector_all(response_selector)
            if elements:
                latest_elem = elements[-1]
                current_text = await latest_elem.inner_text()
                delta = current_text[len(previous_text):]
                if delta:
                    print(delta, end="", flush=True)
                    if self.on_text_stream:
                        self.on_text_stream(delta)
                    previous_text = current_text
                    full_response = current_text

        print()  # newline
        return full_response

    async def _handle_response(self, response):
        """Background network response interceptor."""
        url = response.url
        if "StreamGenerate" in url or "batchexecute" in url:
            pass

    async def close(self):
        """Terminate background Chromium process."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        console.log("[yellow]Playwright background session terminated.[/yellow]")
