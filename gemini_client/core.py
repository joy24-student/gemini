# -*- coding: utf-8 -*-
#########################################
# Core – Unofficial Gemini Client Engine
# Uses: httpx HTTP/2 AsyncClient, orjson,
# pre-compiled regex, and connection keep-alive.
#########################################
import asyncio
import os
import random
import re
import string
from pathlib import Path
from datetime import datetime
from typing import AsyncIterator, Dict, List, Union, Optional

# ── Fast JSON (orjson is 3-5x faster than stdlib json) ─────────────────────
try:
    import orjson  # type: ignore
    def _json_loads(s):  return orjson.loads(s)
    def _json_dumps(o):  return orjson.dumps(o).decode()
except ImportError:
    import json as _json
    def _json_loads(s):  return _json.loads(s)
    def _json_dumps(o):  return _json.dumps(o, ensure_ascii=False)

import json  # still needed for file I/O

from gemini_client.enums import Endpoint, Headers, Model
from gemini_client.cookie_manager import CookieExtractor
from gemini_client.response import (
    GenerateContentResponse, build_response, build_error_response
)
from gemini_client.schema import extract_response

# High-performance async HTTP client (httpx HTTP/2 support)
import httpx
from requests.exceptions import RequestException, Timeout, HTTPError

from pydantic import BaseModel, field_validator
from rich.console import Console
from rich.markdown import Markdown

import sys, io
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

console = Console()


# ── Pre-compiled regex patterns (compiled once at import, reused every call) ─
_RE_SNLM0E      = re.compile(r"""["']SNlM0e["']\s*:\s*["'](.*?)["']""")
_RE_BL          = re.compile(r'"cfb2h":\s*"([^"]+)"')   # Dynamic build label
_RE_IMG_EXT     = re.compile(r'(https?://[^\s]+\.(?:jpg|jpeg|png|gif|webp))', re.I)
_RE_GOOGLE_IMG  = re.compile(r'(https?://lh\d+\.googleusercontent\.com/[^\s]+)')
_RE_ANY_URL     = re.compile(r'(https?://[^\s]+)')
_RE_INLINE_URL  = re.compile(r'https?://[^\s]+')

# -- Build label fallback (dynamically refreshed from page HTML at runtime) ---
_BL = "boq_assistant-bard-web-server_20240625.13_p0"

from gemini_client.utils import upload_file, load_cookies
from gemini_client.memory import ConversationMemory
from gemini_client.schema import extract_response, ProtocolError, _monitor as _protocol_monitor, _walk_for_text
from gemini_client.sync_bridge import SyncStreamBridge

class Chatbot:
    """
    Synchronous wrapper for the AsyncChatbot class.

    This class provides a synchronous interface to interact with Google Gemini,
    handling authentication, conversation management, and message sending.

    Attributes:
        loop (asyncio.AbstractEventLoop): Event loop for running async tasks.
        secure_1psid (str): Authentication cookie.
        secure_1psidts (str): Authentication cookie.
        async_chatbot (AsyncChatbot): Underlying asynchronous chatbot instance.
    """
    def __init__(
        self,
        cookie_path: Optional[str] = None,
        auto_cookie: bool = False,
        proxy: Optional[Union[str, Dict[str, str]]] = None,
        timeout: int = 20,
        model: Model = Model.UNSPECIFIED,
        impersonate: str = "chrome110",
        session_name: Optional[str] = None,
        system_instruction: Optional[str] = None,
        memory: Optional[ConversationMemory] = None,
    ):
        """
        Parameters
        ----------
        cookie_path : str, optional
            Path to a JSON cookie file. Required when auto_cookie=False.
        auto_cookie : bool
            If True, automatically extract cookies from a locally installed browser.
        proxy : str | dict, optional
            Proxy URL string or dict (e.g. {"http": "...", "https": "..."}).
        timeout : int
            Request timeout in seconds.
        model : Model
            Gemini model to use. Defaults to UNSPECIFIED.
        impersonate : str
            Browser profile to impersonate. Default "chrome110".
        session_name : str, optional
            Named memory session for automatic auto-save and auto-resume.
        system_instruction : str, optional
            System prompt instructions.
        memory : ConversationMemory, optional
            Custom ConversationMemory instance.
        """
        # Handle event loop
        try:
            self.loop = asyncio.get_running_loop()
        except RuntimeError:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

        if auto_cookie:
            extractor = CookieExtractor()
            cookie_data = extractor.extract_cookies(save_to_disk=False)
            self.secure_1psid = cookie_data['__Secure-1PSID']
            self.secure_1psidts = cookie_data['__Secure-1PSIDTS']
        else:
            if not cookie_path:
                raise ValueError(
                    "cookie_path is required when auto_cookie=False. "
                    "Provide a path to your cookies JSON file or set auto_cookie=True."
                )
            self.secure_1psid, self.secure_1psidts = load_cookies(cookie_path)

        self.async_chatbot = self.loop.run_until_complete(
            AsyncChatbot.create(
                self.secure_1psid, self.secure_1psidts,
                proxy, timeout, model, impersonate,
                session_name=session_name,
                system_instruction=system_instruction,
                memory=memory,
            )
        )
        self.memory = self.async_chatbot.memory

    def save_conversation(self, file_path: str, conversation_name: str):
        return self.loop.run_until_complete(
            self.async_chatbot.save_conversation(file_path, conversation_name)
        )

    def load_conversations(self, file_path: str) -> List[Dict]:
        return self.loop.run_until_complete(
            self.async_chatbot.load_conversations(file_path)
        )

    def load_conversation(self, file_path: str, conversation_name: str) -> bool:
        return self.loop.run_until_complete(
            self.async_chatbot.load_conversation(file_path, conversation_name)
        )

    def ask(self, message: str, image: Optional[Union[bytes, str, Path]] = None) -> dict:
        """Synchronous ask — blocks until the full response is received."""
        return self.loop.run_until_complete(self.async_chatbot.ask(message, image=image))

    def ask_stream(self, message: str, image: Optional[Union[bytes, str, Path]] = None):
        """
        True synchronous streaming ask — yields text chunks as they arrive in real time.

        Runs the async generator on self.loop and yields chunks to the calling thread
        via a thread-safe Queue, preserving event loop affinity for AsyncChatbot.

        Usage::

            for chunk in chatbot.ask_stream("Tell me a story"):
                print(chunk, end="", flush=True)

        Yields
        ------
        str
            Incremental text content chunks.
        """
        import queue
        import threading

        q = queue.Queue(maxsize=256)
        sentinel = object()
        error_sentinel = object()

        async def _producer():
            try:
                async for chunk in self.async_chatbot.ask_stream(message, image=image):
                    q.put(chunk)
                q.put(sentinel)
            except Exception as e:
                q.put((error_sentinel, e))

        def _run_producer():
            self.loop.run_until_complete(_producer())

        t = threading.Thread(target=_run_producer, daemon=True)
        t.start()

        while True:
            item = q.get()
            if item is sentinel:
                break
            if isinstance(item, tuple) and len(item) == 2 and item[0] is error_sentinel:
                raise item[1]
            yield item

class AsyncChatbot:
    """
    Asynchronous chatbot client for interacting with Google Gemini using curl_cffi.

    This class manages authentication, session state, conversation history,
    and sending/receiving messages (including images) asynchronously.

    Attributes:
        headers (dict): HTTP headers for requests.
        _reqid (int): Request identifier for Gemini API.
        SNlM0e (str): Session token required for API requests.
        conversation_id (str): Current conversation ID.
        response_id (str): Current response ID.
        choice_id (str): Current choice ID.
        proxy (str | dict | None): Proxy configuration.
        proxies_dict (dict | None): Proxy dictionary for curl_cffi.
        secure_1psid (str): Authentication cookie.
        secure_1psidts (str): Authentication cookie.
        session (AsyncSession): curl_cffi session for HTTP requests.
        timeout (int): Request timeout in seconds.
        model (Model): Selected Gemini model.
        impersonate (str): Browser profile for curl_cffi to impersonate.
    """
    __slots__ = [
        "headers",
        "_reqid",
        "SNlM0e",
        "_snlm0e_lock",        # asyncio.Lock – prevents concurrent refreshes
        "conversation_id",
        "response_id",
        "choice_id",
        "proxy",
        "proxies_dict",
        "secure_1psidts",
        "secure_1psid",
        "session",
        "timeout",
        "model",
        "impersonate",
        "_base_params",        # Pre-built params dict (avoids rebuilding each call)
        "_model_name",         # Cached model name string
        "memory",              # ConversationMemory manager
    ]

    def __init__(
        self,
        secure_1psid: str,
        secure_1psidts: str,
        proxy: Optional[Union[str, Dict]] = None,
        timeout: int = 20,
        model: Model = Model.UNSPECIFIED,
        impersonate: str = "chrome110",
        session_name: Optional[str] = None,
        system_instruction: Optional[str] = None,
        memory: Optional[ConversationMemory] = None,
        cookies_dict: Optional[Dict[str, str]] = None,
    ):
        headers = Headers.GEMINI.value.copy()
        if model != Model.UNSPECIFIED:
            headers.update(model.model_header)

        self._reqid = int("".join(random.choices(string.digits, k=7)))
        self.proxy = proxy
        self.impersonate = impersonate
        self._model_name = model.model_name if model != Model.UNSPECIFIED else ""

        # Memory initialization
        if memory is not None:
            self.memory = memory
        else:
            self.memory = ConversationMemory(
                session_name=session_name,
                system_instruction=system_instruction,
            )

        # Proxy dict for httpx
        self.proxies_dict = None
        if isinstance(proxy, str):
            self.proxies_dict = {"http": proxy, "https": proxy}
        elif isinstance(proxy, dict):
            self.proxies_dict = proxy

        self.conversation_id = ""
        self.response_id = ""
        self.choice_id = ""
        self.secure_1psid = secure_1psid
        self.secure_1psidts = secure_1psidts

        client_kwargs = {}
        if isinstance(proxy, str):
            client_kwargs["proxy"] = proxy
        elif isinstance(proxy, dict) and proxy:
            client_kwargs["proxy"] = list(proxy.values())[0]

        # ── Speed: HTTP/2 enabled, connection keep-alive ─────────────────────
        session_cookies = {"__Secure-1PSID": secure_1psid, "__Secure-1PSIDTS": secure_1psidts}
        if cookies_dict and isinstance(cookies_dict, dict):
            session_cookies.update(cookies_dict)

        self.session = httpx.AsyncClient(
            headers=headers,
            cookies=session_cookies,
            timeout=timeout,
            http2=True,
            follow_redirects=True,
            **client_kwargs
        )

        self.timeout = timeout
        self.model = model
        self.SNlM0e = None
        self._snlm0e_lock = asyncio.Lock()  # prevents thundering-herd on token refresh

        # Pre-built request params (only _reqid changes per call)
        self._base_params = {"bl": _BL, "rt": "c"}

    @classmethod
    async def create(
        cls,
        secure_1psid: str,
        secure_1psidts: str,
        proxy: Optional[Union[str, Dict]] = None,
        timeout: int = 20,
        model: Model = Model.UNSPECIFIED,
        impersonate: str = "chrome110",
        session_name: Optional[str] = None,
        system_instruction: Optional[str] = None,
        memory: Optional[ConversationMemory] = None,
        cookies_dict: Optional[Dict[str, str]] = None,
    ) -> "AsyncChatbot":
        """
        Factory: constructs and initialises the chatbot in one step.
        """
        instance = cls(
            secure_1psid, secure_1psidts, proxy, timeout, model, impersonate,
            session_name=session_name, system_instruction=system_instruction, memory=memory,
            cookies_dict=cookies_dict
        )
        try:
            instance.SNlM0e = await instance.__get_snlm0e()
        except Exception as e:
            console.log(f"[red]AsyncChatbot init failed: {e}[/red]", style="bold red")
            await instance.session.aclose()
            raise
        return instance

    async def save_conversation(self, file_path: str, conversation_name: str) -> None:
        # Logic remains the same
        conversations = await self.load_conversations(file_path)
        conversation_data = {
            "conversation_name": conversation_name,
            "_reqid": self._reqid,
            "conversation_id": self.conversation_id,
            "response_id": self.response_id,
            "choice_id": self.choice_id,
            "SNlM0e": self.SNlM0e,
            "model_name": self.model.model_name, # Save the model used
            "timestamp": datetime.now().isoformat(), # Add timestamp
        }

        found = False
        for i, conv in enumerate(conversations):
            if conv.get("conversation_name") == conversation_name:
                conversations[i] = conversation_data # Update existing
                found = True
                break
        if not found:
            conversations.append(conversation_data) # Add new

        try:
            # Ensure directory exists
            Path(file_path).parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(conversations, f, indent=4, ensure_ascii=False)
        except IOError as e:
            console.log(f"[red]Error saving conversation to {file_path}: {e}[/red]")
            raise

    async def load_conversations(self, file_path: str) -> List[Dict]:
        # Logic remains the same
        if not os.path.isfile(file_path):
            return []
        try:
            with open(file_path, 'r', encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            console.log(f"[red]Error loading conversations from {file_path}: {e}[/red]")
            return []

    async def load_conversation(self, file_path: str, conversation_name: str) -> bool:
        # Logic remains the same, but update headers on the session
        conversations = await self.load_conversations(file_path)
        for conversation in conversations:
            if conversation.get("conversation_name") == conversation_name:
                try:
                    self._reqid = conversation["_reqid"]
                    self.conversation_id = conversation["conversation_id"]
                    self.response_id = conversation["response_id"]
                    self.choice_id = conversation["choice_id"]
                    self.SNlM0e = conversation["SNlM0e"]
                    if "model_name" in conversation:
                         try:
                              self.model = Model.from_name(conversation["model_name"])
                              # Update headers in the session if model changed
                              self.session.headers.update(self.model.model_header)
                         except ValueError as e:
                              console.log(f"[yellow]Warning: Model '{conversation['model_name']}' from saved conversation not found. Using current model '{self.model.model_name}'. Error: {e}[/yellow]")

                    console.log(f"Loaded conversation '{conversation_name}'")
                    return True
                except KeyError as e:
                    console.log(f"[red]Error loading conversation '{conversation_name}': Missing key {e}[/red]")
                    return False
        console.log(f"[yellow]Conversation '{conversation_name}' not found in {file_path}[/yellow]")
        return False

    async def __get_snlm0e(self):
        """Fetches the SNlM0e token. Dynamically refreshes the build label from page HTML."""
        global _BL
        if not self.secure_1psid:
            raise ValueError("__Secure-1PSID cookie is required.")
        try:
            resp = await self.session.get(Endpoint.INIT.value, timeout=self.timeout)
            resp.raise_for_status()

            if "Sign in to continue" in resp.text or "accounts.google.com" in str(resp.url):
                raise PermissionError(
                    "Authentication failed. Cookies might be invalid or expired."
                )

            # -- Dynamically update build label (auto-adapts when Google rotates it) -
            bl_match = _RE_BL.search(resp.text)
            if bl_match:
                new_bl = bl_match.group(1)
                if new_bl != _BL:
                    console.log(f"[cyan]Build label updated: {_BL} -> {new_bl}[/cyan]")
                    _BL = new_bl
                    self._base_params["bl"] = _BL

            # Extract session token using multi-strategy fallback
            token = None

            # Strategy A: Legacy SNlM0e key
            m = _RE_SNLM0E.search(resp.text)
            if m:
                token = m.group(1)

            # Strategy B: Extract from WIZ_global_data object (CAMS / AFW / AG / AH session tokens)
            if not token:
                wiz_match = re.search(r'WIZ_global_data\s*=\s*(\{.*?\});', resp.text, re.DOTALL)
                if wiz_match:
                    try:
                        token_matches = re.findall(r'["\']((?:CAMS|AFW|AG|AH)[a-zA-Z0-9_\-\:]{20,})["\']', wiz_match.group(1))
                        if token_matches:
                            token = token_matches[0]
                    except Exception:
                        pass

            # Strategy C: General fallback regex scan over entire HTML
            if not token:
                token_matches = re.findall(r'["\']((?:CAMS|AFW|AG|AH)[a-zA-Z0-9_\-\:]{20,})["\']', resp.text)
                if token_matches:
                    token = token_matches[0]

            if not token:
                code = resp.status_code
                hint = " (rate-limited)" if code == 429 else f" (HTTP {code})"
                raise ValueError(f"SNlM0e token not found{hint}. Check cookies.")

            # Try to refresh PSIDTS
            if not self.secure_1psidts and "PSIDTS" not in self.session.cookies:
                try:
                    await self.__rotate_cookies()
                except Exception:
                    pass

            return token

        except (Timeout, TimeoutError, httpx.TimeoutException) as e:
            raise TimeoutError(f"Timeout fetching SNlM0e: {e}") from e
        except (RequestException, httpx.RequestError) as e:
            raise ConnectionError(f"Network error fetching SNlM0e: {e}") from e
        except (HTTPError, httpx.HTTPStatusError) as e:
            status = getattr(getattr(e, 'response', None), 'status_code', '?')
            if status in (401, 403):
                raise PermissionError(f"Auth failed ({status}). Refresh cookies.") from e
            raise Exception(f"HTTP {status} fetching SNlM0e: {e}") from e

    async def __rotate_cookies(self):
        """Rotates the __Secure-1PSIDTS cookie."""
        try:
            response = await self.session.post(
                Endpoint.ROTATE_COOKIES.value,
                headers=Headers.ROTATE_COOKIES.value,
                data='[000,"-0000000000000000000"]',
                timeout=self.timeout
            )
            response.raise_for_status()

            if new_1psidts := response.cookies.get("__Secure-1PSIDTS"):
                self.secure_1psidts = new_1psidts
                self.session.cookies.set("__Secure-1PSIDTS", new_1psidts)
                return new_1psidts
        except Exception as e:
            console.log(f"[yellow]Cookie rotation failed: {e}[/yellow]")
            raise


    async def _refresh_snlm0e(self) -> None:
        """
        Re-fetch the SNlM0e token when session has expired.
        Lock-protected to prevent duplicate concurrent refresh requests.
        """
        async with self._snlm0e_lock:
            console.log("[yellow]🔄 Session token expired — refreshing SNlM0e...[/yellow]")
            try:
                await self.__rotate_cookies()
            except Exception:
                pass  # Rotation may fail — still try to fetch new token
            try:
                self.SNlM0e = await self.__get_snlm0e()
                console.log("[green]✅ SNlM0e refreshed successfully[/green]")
            except Exception as e:
                console.log(f"[red]❌ SNlM0e refresh failed: {e}[/red]")
                raise

    async def ask(
        self,
        message: str,
        image: Optional[Union[bytes, str, Path]] = None,
        retry: int = 3,
        retry_delay: float = 1.5,
    ) -> GenerateContentResponse:
        """
        Sends a message to Google Gemini and returns a GenerateContentResponse.

        Parameters
        ----------
        message : str
            The message to send.
        image : bytes | str | Path, optional
            Image data or path to include in the message.
        retry : int
            Number of automatic retries on transient network errors. Default 3.
        retry_delay : float
            Base delay between retries (exponential backoff). Default 1.5s.

        Returns
        -------
        GenerateContentResponse
            Official API-style response object with .text, .candidates, .usage_metadata, etc.
            Also supports dict-style access (e.g. response["content"]).
        """
        if self.SNlM0e is None:
            raise RuntimeError("AsyncChatbot not properly initialized. Call AsyncChatbot.create()")

        if self.memory:
            self.memory.add_user_message(message)

        last_raw = None
        for attempt in range(1, retry + 1):
            last_raw = await self._ask_once(message, image=image)
            if not isinstance(last_raw, dict):
                last_raw = {"content": "Unknown response from _ask_once", "error": True}

            # If successful, return constructed GenerateContentResponse
            if not last_raw.get("error"):
                resp = build_response(last_raw, model_name=self._model_name)
                if self.memory and resp.text:
                    self.memory.add_model_message(resp.text)
                return resp

            error_content = last_raw.get("content", "")

            # Check for auth/session expiry — refresh SNlM0e and retry once
            if any(kw in str(error_content) for kw in ["401", "403", "Authentication", "SNlM0e"]):
                if attempt == 1:
                    try:
                        await self._refresh_snlm0e()
                        continue  # retry immediately after refresh
                    except Exception:
                        resp = build_response(last_raw, model_name=self._model_name)
                        if self.memory and resp.text:
                            self.memory.add_model_message(resp.text)
                        return resp

            # Transient network error retry with exponential backoff
            if any(kw in str(error_content) for kw in ["timed out", "Network error", "ConnectionError"]):
                if attempt < retry:
                    delay = retry_delay * (2 ** (attempt - 1))
                    console.log(f"[yellow]⚠️ Retrying in {delay:.1f}s (attempt {attempt}/{retry})...[/yellow]")
                    await asyncio.sleep(delay)
                    continue

            resp = build_response(last_raw, model_name=self._model_name)
            if self.memory and resp.text:
                self.memory.add_model_message(resp.text)
            return resp

        return build_error_response(f"Request failed after {retry} attempts.", model_name=self._model_name)

    async def ask_stream(
        self,
        message: str,
        image: Optional[Union[bytes, str, Path]] = None,
    ) -> AsyncIterator[str]:
        """
        Streaming ask: yields text chunks as they arrive.
        """
        if self.SNlM0e is None:
            raise RuntimeError("AsyncChatbot not properly initialized. Call AsyncChatbot.create()")

        if self.memory:
            self.memory.add_user_message(message)

        params = self._base_params.copy()
        params["_reqid"] = str(self._reqid)

        # Handle optional image upload
        image_upload_id = None
        if image:
            try:
                bot_cookies = dict(self.session.cookies) if hasattr(self, 'session') and hasattr(self.session, 'cookies') else None
                image_upload_id = await upload_file(image, proxy=self.proxies_dict, impersonate=self.impersonate, cookies=bot_cookies)
                console.log(f"Image uploaded successfully. ID: {image_upload_id}")
            except Exception as e:
                console.log(f"[red]Error uploading image: {e}[/red]")
                yield f"[Error uploading image: {e}]"
                return

        if image_upload_id:
            message_struct = [
                [message, 0, None, [[[image_upload_id], "image.jpg"]]],
                None,
                [self.conversation_id, self.response_id, self.choice_id],
            ]
        else:
            message_struct = [
                [message],
                None,
                [self.conversation_id, self.response_id, self.choice_id],
            ]

        resp = None
        for attempt in range(2):
            data = {
                "f.req": _json_dumps([None, _json_dumps(message_struct)]),
                "at": self.SNlM0e,
            }
            try:
                resp = await self.session.post(
                    Endpoint.GENERATE.value,
                    params=params,
                    data=data,
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                break
            except Exception as e:
                status = getattr(getattr(e, 'response', None), 'status_code', None)
                if status == 400 and image_upload_id:
                    # Fallback to standard text message_struct if Google RPC rejects image_upload_id
                    message_struct = [
                        [message],
                        None,
                        [self.conversation_id, self.response_id, self.choice_id],
                    ]
                    continue
                if attempt == 0 and (status in (401, 403) or "401" in str(e) or "403" in str(e)):
                    try:
                        await self._refresh_snlm0e()
                        continue
                    except Exception:
                        pass
                yield f"[Stream error: {e}]"
                return

        final_conversation_id = self.conversation_id
        final_response_id = self.response_id
        final_choice_id = self.choice_id
        accumulated_text = ""

        has_wrb = False
        has_text = False

        # Parse streaming response line-by-line using fast _json_loads
        print(f"DEBUG RESP.TEXT: {resp.text[:500]}...", flush=True)
        lines = resp.text.splitlines()
        for line in lines:
            if not line or line == ")]}'":
                continue
            if line.startswith(")]}"):
                line = line[4:].strip()
            if not line.startswith("["):
                continue
            try:
                response_json = _json_loads(line)
                for part in response_json:
                    if isinstance(part, list) and part and part[0] == "error":
                        yield f"\n[Google API Error: {part}]\n"
                        has_text = True
                        continue
                    if not (isinstance(part, list) and len(part) > 2 and part[0] == "wrb.fr"):
                        continue
                    # Detect BardErrorInfo and extract exact error code
                    if len(part) > 5 and part[5]:
                        err_str = str(part[5])
                        if "BardErrorInfo" in err_str or "1096" in err_str or "1100" in err_str:
                            if "1100" in err_str:
                                raise RuntimeError(f"BardErrorInfo 1100: Google Gemini vision backend rejected the uploaded image ({err_str})")
                            elif "1096" in err_str:
                                raise RuntimeError(f"BardErrorInfo 1096: Conversation state expired or invalid session ({err_str})")
                            else:
                                raise RuntimeError(f"BardErrorInfo: Google Gemini returned error ({err_str})")
                    has_wrb = True
                    inner_str = part[2]
                    if not isinstance(inner_str, str):
                        continue
                    try:
                        body = _json_loads(inner_str)
                    except Exception:
                        continue
                    if not body or not (len(body) > 4 and body[4]):
                        continue

                    # Extract text chunk across candidates in body[4] (handles web search & grounding)
                    try:
                        best_chunk = ""
                        if isinstance(body[4], list):
                            for cand in body[4]:
                                if isinstance(cand, list) and len(cand) > 1 and cand[1]:
                                    parts = cand[1] if isinstance(cand[1], list) else [cand[1]]
                                    cand_text_parts = []
                                    for p in parts:
                                        p_node = p
                                        while isinstance(p_node, list) and p_node:
                                            p_node = p_node[0]
                                        if isinstance(p_node, str) and p_node.strip():
                                            lowered = p_node.strip().lower()
                                            if not p_node.startswith(("boq_assistant", "rc_", "c_", "r_", "_")) and lowered not in ("searching the web", "searching...", "thinking...", "thought") and not lowered.startswith(("searching the web", "searching google", "thinking for")):
                                                cand_text_parts.append(p_node)
                                    full_cand_text = "".join(cand_text_parts)
                                    if len(full_cand_text) > len(best_chunk):
                                        best_chunk = full_cand_text
                        if best_chunk and len(best_chunk) > len(accumulated_text):
                            delta = best_chunk[len(accumulated_text):]
                            accumulated_text = best_chunk
                            has_text = True
                            yield delta

                        # Also extract any images/generated images from body schema
                        try:
                            parsed_s = extract_response(body, response_json=response_json)
                            s_imgs = (getattr(parsed_s, "images", []) or []) + (getattr(parsed_s, "generated_images", []) or [])
                            for s_img in s_imgs:
                                if isinstance(s_img, dict) and s_img.get("url"):
                                    s_url = s_img["url"]
                                    if "image_generation_content" in s_url or "data_analysis_tool" in s_url:
                                        continue
                                    s_title = s_img.get("title") or s_img.get("alt") or "Generated Image"
                                    img_md = f"\n\n![{s_title}]({s_url})\n\n"
                                    if s_url not in accumulated_text:
                                        accumulated_text += img_md
                                        has_text = True
                                        yield img_md
                        except Exception:
                            pass
                    except (IndexError, TypeError):
                        pass

                    # Update conversation state
                    try:
                        if isinstance(body, list) and len(body) > 1 and body[1] and isinstance(body[1], list):
                            b1 = body[1]
                            if len(b1) > 1 and isinstance(b1[1], list) and len(b1[1]) > 0:
                                if b1[1][0]:
                                    final_conversation_id = str(b1[1][0])
                                if len(b1[1]) > 1 and b1[1][1]:
                                    final_response_id = str(b1[1][1])
                            elif len(b1) > 0 and isinstance(b1[0], str) and b1[0]:
                                final_conversation_id = str(b1[0])
                                if len(b1) > 1 and b1[1] and isinstance(b1[1], str):
                                    final_response_id = str(b1[1])

                        if isinstance(body, list) and len(body) > 4 and isinstance(body[4], list) and body[4]:
                            for c in body[4]:
                                if isinstance(c, list) and len(c) > 0 and c[0]:
                                    final_choice_id = str(c[0])
                                    break
                    except (IndexError, TypeError):
                        pass
            except RuntimeError as re:
                raise re
            except Exception:
                continue

        if has_wrb and not has_text:
            yield "\n[Message blocked by Google Gemini Safety Filters or returned no text.]"

        # Persist updated conversation state
        self.conversation_id = final_conversation_id
        self.response_id = final_response_id
        self.choice_id = final_choice_id
        self._reqid += random.randint(1000, 9000)

        # Record accumulated text to memory
        if self.memory and accumulated_text:
            self.memory.add_model_message(accumulated_text)

    async def _ask_once(
        self,
        message: str,
        image: Optional[Union[bytes, str, Path]] = None,
    ) -> dict:
        """
        Internal single-attempt ask. Optimized with pre-built params and fast JSON.
        """
        params = self._base_params.copy()
        params["_reqid"] = str(self._reqid)

        # Handle image upload if provided
        image_upload_id = None
        if image:
            try:
                bot_cookies = dict(self.session.cookies) if hasattr(self, 'session') and hasattr(self.session, 'cookies') else None
                image_upload_id = await upload_file(image, proxy=self.proxies_dict, impersonate=self.impersonate, cookies=bot_cookies)
                console.log(f"Image uploaded successfully. ID: {image_upload_id}")
            except Exception as e:
                console.log(f"[red]Error uploading image: {e}[/red]")
                return {"content": f"Error uploading image: {e}", "error": True}

        # Prepare message structure
        if image_upload_id:
            message_struct = [
                [message],
                [[[image_upload_id, 1]]],
                [self.conversation_id, self.response_id, self.choice_id],
            ]
        else:
            message_struct = [
                [message],
                None,
                [self.conversation_id, self.response_id, self.choice_id],
            ]

        data = {
            "f.req": _json_dumps([None, _json_dumps(message_struct)]),
            "at": self.SNlM0e,
        }


        try:
            try:
                # Send request
                resp = await self.session.post(
                    Endpoint.GENERATE.value,
                    params=params,
                    data=data,
                    timeout=self.timeout,
                )
                resp.raise_for_status()
            except (HTTPError, httpx.HTTPStatusError) as e:
                status = getattr(getattr(e, 'response', None), 'status_code', None)
                if status == 400 and image_upload_id:
                    # Fallback to standard text message_struct if Google RPC rejects image_upload_id
                    fb_struct = [
                        [message],
                        None,
                        [self.conversation_id, self.response_id, self.choice_id],
                    ]
                    fb_data = {
                        "f.req": _json_dumps([None, _json_dumps(fb_struct)]),
                        "at": self.SNlM0e,
                    }
                    resp = await self.session.post(
                        Endpoint.GENERATE.value,
                        params=params,
                        data=fb_data,
                        timeout=self.timeout,
                    )
                    resp.raise_for_status()
                else:
                    raise

            # Process response
            lines = resp.text.splitlines()
            if len(lines) < 3:
                raise ValueError(f"Unexpected response format. Status: {resp.status_code}. Content: {resp.text[:200]}...")

            body = None
            body_index = 0
            response_json = None

            for line in lines:
                if not line or line == ")]}'":
                    continue
                if line.startswith(")]}"):
                    line = line[4:].strip()
                if not line.startswith("["):
                    continue
                try:
                    response_json = json.loads(line)
                    for part_index, part in enumerate(response_json):
                        try:
                            if isinstance(part, list) and len(part) > 2 and part[0] == "wrb.fr":
                                inner_json_str = part[2]
                                if isinstance(inner_json_str, str):
                                    main_part = json.loads(inner_json_str)
                                    if isinstance(main_part, list):
                                        has_choices = len(main_part) > 4 and isinstance(main_part[4], list) and main_part[4]
                                        has_text = any(not c.startswith(("rc_", "c_", "boq_", "_")) and len(c) > 3 for c in _walk_for_text(main_part))
                                        if has_choices or has_text:
                                            body = main_part
                                            body_index = part_index
                                            break
                        except (IndexError, TypeError, json.JSONDecodeError):
                            continue
                    if body:
                        break
                except json.JSONDecodeError:
                    continue

            if not body:
                return {"content": "Failed to parse response body. No valid data found.", "error": True}

            try:
                # ── Adaptive schema walker replaces all hardcoded indices ────────
                parsed = extract_response(
                    body,
                    response_json=response_json,
                    current_conversation_id=self.conversation_id,
                    current_response_id=self.response_id,
                    current_choice_id=self.choice_id,
                )
                # Record structural fingerprint for protocol drift monitoring
                _protocol_monitor.record(body)
                if _protocol_monitor.check_drift():
                    console.log("[bold yellow][WARNING] Protocol drift detected: Google may have changed the Web UI RPC schema. Check schema.py.[/bold yellow]")
                if parsed.degraded:
                    console.log("[yellow][INFO] Schema fast-path missed — using fallback walker. Response parsed successfully.[/yellow]")

                factualityQueries = body[3] if isinstance(body, list) and len(body) > 3 else None
                textQuery = ""
                if isinstance(body, list) and len(body) > 2 and isinstance(body[2], list) and body[2]:
                    textQuery = str(body[2][0]) if body[2][0] is not None else ""

                imgs = parsed.images if isinstance(getattr(parsed, "images", None), list) else []
                gen_imgs = parsed.generated_images if isinstance(getattr(parsed, "generated_images", None), list) else []
                all_images = imgs + gen_imgs

                choices_val = parsed.choices if isinstance(getattr(parsed, "choices", None), list) else []

                results = {
                    "content": parsed.text or "",
                    "conversation_id": parsed.conversation_id or "",
                    "response_id": parsed.response_id or "",
                    "factualityQueries": factualityQueries,
                    "textQuery": textQuery,
                    "choices": choices_val,
                    "images": all_images,
                    "error": False,
                }

                self.conversation_id = parsed.conversation_id
                self.response_id     = parsed.response_id
                self.choice_id       = parsed.choice_id
                self._reqid += random.randint(1000, 9000)

                return results

            except ProtocolError as e:
                console.log(f"[bold red][ERROR] Protocol error — schema may have changed: {e}[/bold red]")
                return {"content": f"Protocol error: {e}", "error": True}
            except (IndexError, TypeError) as e:
                console.log(f"[red]Error extracting data from response: {e}[/red]")
                return {"content": f"Error extracting data from response: {e}", "error": True}

        except json.JSONDecodeError as e:
            console.log(f"[red]Error parsing JSON response: {e}[/red]")
            return {"content": f"Error parsing JSON response: {e}. Response: {resp.text[:200]}...", "error": True}
        except (Timeout, TimeoutError, httpx.TimeoutException) as e:
            console.log(f"[red]Request timed out: {e}[/red]")
            return {"content": f"Request timed out: {e}", "error": True}
        except (RequestException, httpx.RequestError) as e:
            console.log(f"[red]Network error: {e}[/red]")
            return {"content": f"Network error: {e}", "error": True}
        except (HTTPError, httpx.HTTPStatusError) as e:
            status = getattr(getattr(e, 'response', None), 'status_code', '?')
            console.log(f"[red]HTTP error {status}: {e}[/red]")
            return {"content": f"HTTP error {status}: {e}", "error": True}
        except Exception as e:
            console.log(f"[red]An unexpected error occurred during ask: {e}[/red]", style="bold red")
            return {"content": f"An unexpected error occurred: {e}", "error": True}


#########################################
# Imports for refactored classes
#########################################
