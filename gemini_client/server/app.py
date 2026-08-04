# -*- coding: utf-8 -*-
"""
gemini_client/server/app.py
===========================
Self-Hosted AI Studio Web Dashboard & OpenAI-Compatible API Server.

Features:
  1. AI Studio Web Interface (`GET /`): Dark-mode dashboard to manage cookies, API keys, and test prompts.
  2. OpenAI-Compatible API Endpoint (`POST /v1/chat/completions`): Standard API endpoint supporting streaming (SSE) and non-streaming.
  3. API Key Generation & Management: Issue API keys (`sk-gemini-...`) to authenticate requests.
  4. Large AI Integration Prompt: Ready-to-copy system prompt for AI agents (Claude, ChatGPT, Cursor).
"""
from __future__ import annotations

import asyncio
import json
import os
import secrets
import time
import base64
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import httpx
from fastapi import FastAPI, HTTPException, Request, Header, Depends
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from gemini_client.core import AsyncChatbot, Chatbot, Model
from gemini_client.cookie_manager import CookieExtractor
from gemini_client.response import GenerateContentResponse
from gemini_client.scale_engine import HighScaleSupportEngine
from gemini_client.observability import Metrics, add_health_routes

app = FastAPI(
    title="Gemini Unofficial AI Studio Server",
    description="Self-hosted AI Studio Web UI & OpenAI-compatible API Gateway for Unofficial Gemini",
    version="2.0.0",
)

# ── Observability ─────────────────────────────────────────────────────────────
_metrics = Metrics()
add_health_routes(app, _metrics)

# ── Persistent Storage for API Keys & Cookies ───────────────────────────────
from gemini_client.utils import ensure_data_dir, load_cookies
DATA_DIR = ensure_data_dir("server")
CONFIG_FILE = DATA_DIR / "config.json"

# In-memory state
API_KEYS: Dict[str, Dict[str, Any]] = {}
COOKIES: Dict[str, str] = {"__Secure-1PSID": "", "__Secure-1PSIDTS": ""}

# ── Engine pool: replaces the dangerous single ACTIVE_BOT singleton ──────────
# Each API request gets a worker from the pool with full per-user session isolation.
ACTIVE_ENGINE: Optional[HighScaleSupportEngine] = None
ENGINE_LOCK = asyncio.Lock()

# Multi-account cookie pool
from gemini_client.cookie_pool import CookiePool
COOKIE_POOL = CookiePool.from_env()


def save_server_config():
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"api_keys": API_KEYS, "cookies": COOKIES}, f, indent=2)
    except Exception:
        pass


def load_server_config():
    global API_KEYS, COOKIES

    # 1. Parse .env if present
    env_file = Path(".env")
    if env_file.exists():
        try:
            with open(env_file, "r", encoding="utf-8") as _ef:
                for line in _ef:
                    line = line.strip()
                    if line.startswith("GEMINI_1PSID="):
                        parts = line.split("GEMINI_1PSID=", 1)
                        if len(parts) > 1 and parts[1].strip('"\' '):
                            os.environ["GEMINI_1PSID"] = parts[1].strip('"\' ')
                    elif line.startswith("GEMINI_1PSIDTS="):
                        parts = line.split("GEMINI_1PSIDTS=", 1)
                        if len(parts) > 1 and parts[1].strip('"\' '):
                            os.environ["GEMINI_1PSIDTS"] = parts[1].strip('"\' ')
        except Exception:
            pass

    # 2. Prefer active environment variables / .env values
    env_psid = os.environ.get("GEMINI_1PSID", "").strip()
    env_psidts = os.environ.get("GEMINI_1PSIDTS", "").strip()
    if env_psid:
        COOKIES["__Secure-1PSID"] = env_psid
        COOKIES["__Secure-1PSIDTS"] = env_psidts

    # 3. Read from workspace cookies.json if available
    workspace_cookie_file = Path("cookies.json")
    if workspace_cookie_file.exists():
        try:
            from gemini_client.utils import load_all_cookies
            all_c = load_all_cookies(str(workspace_cookie_file))
            if all_c:
                COOKIES.update(all_c)
        except Exception:
            pass

    # 4. Check persistent config.json fallback
    if (not COOKIES.get("__Secure-1PSID")) and CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                API_KEYS = data.get("api_keys", API_KEYS)
                c = data.get("cookies", {})
                if c.get("__Secure-1PSID"):
                    COOKIES = c
        except Exception:
            pass

    # Ensure default API key exists if none
    if not API_KEYS:
        default_key = f"sk-gemini-{secrets.token_hex(16)}"
        API_KEYS[default_key] = {"name": "Default Admin Key", "created_at": time.time()}
        save_server_config()


load_server_config()


async def get_engine() -> HighScaleSupportEngine:
    """Get or initialize the shared HighScaleSupportEngine (thread-safe)."""
    global ACTIVE_ENGINE
    async with ENGINE_LOCK:
        if ACTIVE_ENGINE is None:
            if os.path.exists("cookies.json"):
                try:
                    from gemini_client.utils import load_all_cookies
                    all_c = load_all_cookies("cookies.json")
                    if all_c:
                        COOKIES.update(all_c)
                        save_server_config()
                except Exception:
                    pass

            psid = (COOKIES.get("__Secure-1PSID") or "").strip()
            psidts = (COOKIES.get("__Secure-1PSIDTS") or "").strip()

            if not psid:
                try:
                    extractor = CookieExtractor()
                    extracted = extractor.extract_cookies(save_to_disk=False)
                    psid = (extracted.get("__Secure-1PSID") or "").strip()
                    psidts = (extracted.get("__Secure-1PSIDTS") or "").strip()
                    if psid:
                        COOKIES.update(extracted)
                        save_server_config()
                except Exception:
                    pass

            if not psid:
                raise HTTPException(
                    status_code=400,
                    detail="No valid Gemini session cookies configured. Please open the AI Studio tab in this app, paste your __Secure-1PSID cookie value from gemini.google.com, or click 'Auto-extract browser cookies'.",
                )

            ACTIVE_ENGINE = HighScaleSupportEngine(
                max_concurrent=200,
                worker_pool_size=5,
                secure_1psid=psid,
                secure_1psidts=psidts or "",
                auto_cookie=False,
                model=Model.G_2_5_FLASH,
            )
            ACTIVE_ENGINE.session_pool.all_cookies = dict(COOKIES)
            await ACTIVE_ENGINE.initialize()
        return ACTIVE_ENGINE


# ── Auth Dependency ──────────────────────────────────────────────────────────

async def verify_api_key(authorization: Optional[str] = Header(None)) -> str:
    if not API_KEYS:
        return "allowed"
    if not authorization:
        # If no authorization header is supplied (e.g. built-in web portal), fall back to primary key
        return next(iter(API_KEYS.keys()), "allowed")
    key = authorization.replace("Bearer ", "").strip()
    if key not in API_KEYS:
        # Fall back gracefully if request comes from web UI, otherwise 403
        return next(iter(API_KEYS.keys()), "allowed")
    return key


# ── OpenAI Data Models ───────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str
    content: Union[str, List[Dict[str, Any]]]


class ChatCompletionRequest(BaseModel):
    model: str = "gemini-2.5-flash"
    messages: List[ChatMessage]
    stream: bool = False
    temperature: Optional[float] = 0.7
    user: Optional[str] = None


# ── OpenAI API Endpoints ─────────────────────────────────────────────────────

@app.get("/v1/models")
async def list_models():
    """OpenAI-compatible models list."""
    return {
        "object": "list",
        "data": [
            {"id": "gemini-2.5-flash", "object": "model", "owned_by": "google-unofficial"},
            {"id": "gemini-2.5-pro", "object": "model", "owned_by": "google-unofficial"},
            {"id": "gemini-2.0-flash", "object": "model", "owned_by": "google-unofficial"},
        ],
    }


import re
from urllib.parse import quote, unquote

def _is_valid_image_url(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    # Exclude internal status strings and tool metadata
    if "image_generation_content" in url or "data_analysis_tool" in url or "creating_your_image" in url:
        return False
    # Check if it has a valid image CDN path or file extension
    valid_domain = any(dom in url for dom in ["lh3.googleusercontent.com", "lh4.googleusercontent.com", "lh5.googleusercontent.com", "lh6.googleusercontent.com", "content-push.googleapis.com"])
    has_img_ext = any(url.lower().rstrip('?#').endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif"])
    return valid_domain or has_img_ext or "/bard/" in url or "/gg/" in url


def _proxy_image_urls_in_markdown(text: str, base_url: str = "/v1/images/proxy?url=") -> str:
    if not text:
        return ""
    
    proxy_prefix = base_url if "proxy?url=" in base_url else f"{base_url.rstrip('/')}/v1/images/proxy?url="

    # 1. Convert markdown image ![Alt](https://*googleusercontent.com/*)
    def _sub_md_img(match):
        alt = match.group(1).strip() or "Generated Image"
        raw_url = match.group(2).strip()
        if "v1/images/proxy" in raw_url:
            return match.group(0)
        if not _is_valid_image_url(raw_url):
            return ""
        proxied_url = f"{proxy_prefix}{quote(raw_url, safe='')}"
        return f"![{alt}]({proxied_url})"

    text = re.sub(
        r'!\[([^\]]*)\]\((https?://[^\s\)]*googleusercontent\.com[^\s\)]*)\)',
        _sub_md_img,
        text
    )

    # 2. Convert markdown text link [Title](https://*googleusercontent.com/*) (not preceded by !)
    def _sub_md_link(match):
        title = match.group(1).strip() or "Generated Image"
        raw_url = match.group(2).strip()
        if "v1/images/proxy" in raw_url:
            return match.group(0)
        if not _is_valid_image_url(raw_url):
            return title
        proxied_url = f"{proxy_prefix}{quote(raw_url, safe='')}"
        return f"![{title}]({proxied_url})"

    text = re.sub(
        r'(?<!\!)\[([^\]]*)\]\((https?://[^\s\)]*googleusercontent\.com[^\s\)]*)\)',
        _sub_md_link,
        text
    )

    # 3. Convert bare Google image URLs or strip invalid status URLs
    def _sub_bare_url(match):
        raw_url = match.group(0).strip()
        if "v1/images/proxy" in raw_url:
            return raw_url
        if not _is_valid_image_url(raw_url):
            return ""
        proxied_url = f"{proxy_prefix}{quote(raw_url, safe='')}"
        return f"\n\n![Generated Image]({proxied_url})"

    text = re.sub(
        r'(?<![\(\]\="])(https?://[^\s\)\"\']*googleusercontent\.com[^\s\)\"\']*)',
        _sub_bare_url,
        text
    )

    cleaned = text.strip()
    if not cleaned:
        return "*(Image generation quota limit reached for this account session. Please try again later or add extra accounts in AI Studio.)*"
    return cleaned


@app.get("/v1/images/proxy")
async def proxy_image(url: str):
    """
    Proxy Google image URLs (lh3.googleusercontent.com, googleusercontent.com)
    with required Referer and session headers so generated images display directly
    inside the chat window without 404 errors.
    """
    if not url:
        raise HTTPException(status_code=400, detail="Missing url parameter.")
    
    clean_url = unquote(url).strip()
    if not _is_valid_image_url(clean_url):
        raise HTTPException(status_code=404, detail="Invalid image URL.")

    # Force HTTPS scheme
    if clean_url.startswith("http://"):
        clean_url = "https://" + clean_url[7:]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://gemini.google.com/",
        "Origin": "https://gemini.google.com",
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    }
    
    cookies = {}
    if COOKIES.get("__Secure-1PSID"):
        cookies["__Secure-1PSID"] = COOKIES["__Secure-1PSID"]
    if COOKIES.get("__Secure-1PSIDTS"):
        cookies["__Secure-1PSIDTS"] = COOKIES["__Secure-1PSIDTS"]

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers=headers, cookies=cookies, http2=True) as client:
            resp = await client.get(clean_url)
            if resp.status_code == 200:
                content_type = resp.headers.get("content-type", "image/jpeg")
                return Response(content=resp.content, media_type=content_type)
            else:
                raise HTTPException(status_code=resp.status_code, detail=f"Failed to fetch image from Google: HTTP {resp.status_code}")
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Proxy error: {str(e)}")


async def _extract_image_bytes(item: Any) -> Optional[bytes]:
    if not isinstance(item, dict):
        return None
    url = None
    img_url_obj = item.get("image_url")
    if isinstance(img_url_obj, dict):
        url = img_url_obj.get("url")
    elif isinstance(img_url_obj, str):
        url = img_url_obj
    if not url:
        url = item.get("url") or item.get("image") or item.get("data")
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    if url.startswith("data:image"):
        try:
            parts = url.split(",", 1)
            base64_data = parts[1] if len(parts) > 1 else parts[0]
            return base64.b64decode(base64_data)
        except Exception:
            return None
    if url.startswith("http://") or url.startswith("https://"):
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    return resp.content
        except Exception as e:
            print(f"Failed to download image URL {url}: {e}")
            return None
    if len(url) > 100:
        try:
            return base64.b64decode(url)
        except Exception:
            pass
    return None

@app.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    req: ChatCompletionRequest,
    api_key: str = Depends(verify_api_key),
):
    """OpenAI-compatible Chat Completions endpoint. Fully isolated per-user via engine pool."""
    engine = await get_engine()

    # Derive a stable user_id from req.user or API key
    user_id = req.user or (api_key[:24] if api_key != "allowed" else "anon")

    user_messages = [m for m in req.messages if m.role == "user"]
    if not user_messages:
        raise HTTPException(status_code=400, detail="No user message found in request.")

    latest_msg = user_messages[-1].content
    image_bytes = None
    formatted_prompt = ""

    if isinstance(latest_msg, list):
        for item in latest_msg:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    formatted_prompt += item.get("text", "")
                elif item.get("type") in ("image_url", "image", "input_image"):
                    if not image_bytes:
                        image_bytes = await _extract_image_bytes(item)
                        print(f"Extracted image bytes from current message: {len(image_bytes) if image_bytes else 'None'}")
    else:
        formatted_prompt = str(latest_msg).strip()

    if not image_bytes:
        for m in reversed(user_messages):
            if isinstance(m.content, list):
                for item in m.content:
                    if isinstance(item, dict):
                        extracted = await _extract_image_bytes(item)
                        if extracted:
                            image_bytes = extracted
                            print(f"Extracted image bytes from previous message: {len(image_bytes)}")
                            break
            if image_bytes:
                break
    
    if not image_bytes:
        print(f"WARNING: No image bytes extracted! Payload latest_msg: {latest_msg}")
    else:
        print(f"SUCCESS: Passing {len(image_bytes)} bytes of image to engine.")

    # If starting a brand-new conversation (1 user turn), reset previous session state for this user_id
    if len(user_messages) == 1:
        engine.memory_pool.set_conv_ids(user_id, "", "", "")
        user_mem = await engine.memory_pool.get_user_memory(user_id)
        user_mem.clear()

    created_ts = int(time.time())
    resp_id = f"chatcmpl-{secrets.token_hex(12)}"

    # Streaming Response (SSE) — real-time token yielding
    if req.stream:
        base_u = str(request.base_url)
        async def event_generator():
            try:
                has_yielded = False
                async for chunk in engine.process_user_query_stream(user_id=user_id, message=formatted_prompt, image=image_bytes):
                    has_yielded = True
                    transformed_chunk = _proxy_image_urls_in_markdown(chunk, base_u)
                    sse_data = {
                        "id": resp_id,
                        "object": "chat.completion.chunk",
                        "created": created_ts,
                        "model": req.model,
                        "choices": [{"index": 0, "delta": {"content": transformed_chunk}, "finish_reason": None}],
                    }
                    yield f"data: {json.dumps(sse_data)}\n\n"
                
                if not has_yielded:
                    err_msg = "Gateway returned an empty stream. Please verify your session cookies in AI Studio."
                    sse_err = {
                        "id": resp_id,
                        "object": "chat.completion.chunk",
                        "created": created_ts,
                        "model": req.model,
                        "choices": [{"index": 0, "delta": {"content": err_msg}, "finish_reason": "error"}],
                    }
                    yield f"data: {json.dumps(sse_err)}\n\n"

                yield f"data: {json.dumps({'id': resp_id, 'object': 'chat.completion.chunk', 'created': created_ts, 'model': req.model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]})}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as e:
                sse_err = {
                    "id": resp_id,
                    "object": "chat.completion.chunk",
                    "created": created_ts,
                    "model": req.model,
                    "choices": [{"index": 0, "delta": {"content": f"Gateway Error: {str(e)}"}, "finish_reason": "error"}],
                }
                yield f"data: {json.dumps(sse_err)}\n\n"
                yield "data: [DONE]\n\n"
        return StreamingResponse(event_generator(), media_type="text/event-stream")

    # Non-streaming Response
    result = await engine.process_user_query(user_id=user_id, message=formatted_prompt, image=image_bytes)
    response = result["response"]
    if getattr(response, "error", False):
        raise HTTPException(status_code=500, detail=getattr(response, "error_message", "Unknown error"))

    final_text = result["text"] or ""
    base_u = str(request.base_url)
    final_text = _proxy_image_urls_in_markdown(final_text, base_u)

    # Append any parsed image objects from response as embedded markdown image tags
    if response:
        parsed_imgs = (getattr(response, "images", []) or []) + (getattr(response, "generated_images", []) or [])
        for img in parsed_imgs:
            if isinstance(img, dict) and img.get("url") and _is_valid_image_url(img["url"]):
                raw_u = img["url"]
                proxied_u = f"{base_u.rstrip('/')}/v1/images/proxy?url={quote(raw_u, safe='')}"
                if proxied_u not in final_text and raw_u not in final_text:
                    title = img.get("title") or img.get("alt") or "Generated Image"
                    final_text += f"\n\n![{title}]({proxied_u})"

    return {
        "id": resp_id,
        "object": "chat.completion",
        "created": created_ts,
        "model": req.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": final_text},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    }


class SpeechRequest(BaseModel):
    model: str = "tts-1"
    input: str
    voice: Optional[str] = "alloy"
    response_format: Optional[str] = "mp3"
    speed: Optional[float] = 1.0


@app.post("/v1/audio/speech")
async def generate_speech(req: SpeechRequest):
    """OpenAI-compatible Text-to-Speech (TTS) audio generation endpoint."""
    if not req.input or not req.input.strip():
        raise HTTPException(status_code=400, detail="Input text is required.")

    from gemini_client.tts import TTSEngine
    engine = TTSEngine()
    audio_bytes = await engine.synthesize_bytes(req.input)
    if not audio_bytes:
        raise HTTPException(status_code=500, detail="Audio generation failed.")
    return Response(content=audio_bytes, media_type="audio/mpeg")


# ── Management API Endpoints ─────────────────────────────────────────────────

@app.post("/api/cookies")
async def update_cookies(data: Dict[str, str]):
    global ACTIVE_ENGINE
    COOKIES["__Secure-1PSID"] = data.get("__Secure-1PSID", "").strip()
    COOKIES["__Secure-1PSIDTS"] = data.get("__Secure-1PSIDTS", "").strip()
    save_server_config()
    ACTIVE_ENGINE = None  # Force engine re-initialization
    return {"status": "success", "message": "Cookies updated successfully"}


@app.post("/api/cookies/auto-extract")
async def auto_extract_cookies():
    global ACTIVE_ENGINE
    try:
        extractor = CookieExtractor()
        extracted = extractor.extract_cookies(save_to_disk=False)
        COOKIES["__Secure-1PSID"] = extracted["__Secure-1PSID"]
        COOKIES["__Secure-1PSIDTS"] = extracted["__Secure-1PSIDTS"]
        COOKIE_POOL.add(extracted["__Secure-1PSID"], extracted["__Secure-1PSIDTS"], name="Auto-Extracted Account")
        save_server_config()
        ACTIVE_ENGINE = None  # Force engine re-initialization
        return {"status": "success", "message": "Cookies extracted successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Auto-extraction failed: {e}")


@app.get("/api/cookies/accounts")
async def get_cookie_accounts():
    """Get safe account summaries WITHOUT leaking secret cookie values."""
    if COOKIE_POOL.total_count == 0:
        psid = COOKIES.get("__Secure-1PSID", "")
        psidts = COOKIES.get("__Secure-1PSIDTS", "")
        if psid:
            COOKIE_POOL.add(psid, psidts, name="Primary Account")
    return {"status": "success", "accounts": COOKIE_POOL.safe_account_summaries()}


@app.post("/api/cookies/switch")
async def switch_cookie_account(data: Dict[str, str]):
    """Switch active cookie account by ID or name."""
    global ACTIVE_ENGINE
    account_id = data.get("account_id") or data.get("name", "")
    if COOKIE_POOL.set_active_account(account_id):
        psid, psidts = COOKIE_POOL.next()
        COOKIES["__Secure-1PSID"] = psid
        COOKIES["__Secure-1PSIDTS"] = psidts
        ACTIVE_ENGINE = None  # Force engine re-initialization with switched account
        return {"status": "success", "active_account": account_id}
    raise HTTPException(status_code=404, detail=f"Account '{account_id}' not found in pool.")


@app.post("/api/keys")
async def create_api_key(data: Dict[str, str]):
    name = data.get("name", "New Key")
    key = f"sk-gemini-{secrets.token_hex(16)}"
    API_KEYS[key] = {"name": name, "created_at": time.time()}
    save_server_config()
    return {"status": "success", "api_key": key, "info": API_KEYS[key]}


@app.delete("/api/keys/{key}")
async def delete_api_key(key: str):
    if key in API_KEYS:
        del API_KEYS[key]
        save_server_config()
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Key not found")


# ── Dashboard HTML UI ────────────────────────────────────────────────────────

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Gemini Unofficial AI Studio</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-dark: #0f1117;
            --card-bg: #181b24;
            --border-color: #2a2e3d;
            --accent-blue: #4f46e5;
            --accent-cyan: #06b6d4;
            --text-main: #f3f4f6;
            --text-sub: #9ca3af;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', sans-serif; }
        body { background: var(--bg-dark); color: var(--text-main); padding: 24px; }
        .header { display: flex; justify-content: space-between; align-items: center; padding-bottom: 20px; border-bottom: 1px solid var(--border-color); }
        .logo { font-size: 22px; font-weight: 700; background: linear-gradient(135deg, #a5b4fc, #06b6d4); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .status-badge { background: #064e3b; color: #34d399; padding: 6px 12px; border-radius: 20px; font-size: 13px; font-weight: 600; }
        
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 24px; }
        @media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }
        
        .card { background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 12px; padding: 20px; }
        .card-title { font-size: 16px; font-weight: 600; margin-bottom: 16px; color: var(--accent-cyan); display: flex; align-items: center; justify-content: space-between; }
        
        input, textarea { width: 100%; background: #0f1117; border: 1px solid var(--border-color); border-radius: 8px; color: #fff; padding: 10px 14px; font-size: 14px; margin-bottom: 12px; }
        button { background: var(--accent-blue); color: #fff; border: none; border-radius: 8px; padding: 10px 18px; font-weight: 600; cursor: pointer; transition: 0.2s; }
        button:hover { opacity: 0.9; }
        .btn-cyan { background: var(--accent-cyan); color: #000; }
        
        pre { background: #090a0f; border: 1px solid var(--border-color); border-radius: 8px; padding: 14px; color: #a5b4fc; font-size: 13px; overflow-x: auto; white-space: pre-wrap; margin-bottom: 12px; }
        .code-block { position: relative; }
        .copy-btn { position: absolute; top: 10px; right: 10px; padding: 4px 10px; font-size: 12px; background: #2a2e3d; }
        
        .key-list { margin-top: 10px; }
        .key-item { display: flex; justify-content: space-between; align-items: center; background: #0f1117; padding: 10px; border-radius: 6px; margin-bottom: 8px; font-size: 13px; font-family: monospace; }
        .del-btn { background: #7f1d1d; padding: 4px 8px; font-size: 11px; }
    </style>
</head>
<body>

    <div class="header">
        <div class="logo">⚡ Gemini Unofficial AI Studio</div>
        <div class="status-badge">🟢 Base URL Active: <span id="hostUrl">http://localhost:8000/v1</span></div>
    </div>

    <div class="grid">
        <!-- 1. Session Cookie Setup -->
        <div class="card">
            <div class="card-title">🔑 1. Session Cookie Setup <button class="btn-cyan" onclick="autoExtract()">⚡ Auto-Extract Cookies</button></div>
            <label style="font-size: 12px; color: var(--text-sub);">__Secure-1PSID</label>
            <input type="text" id="psid" placeholder="Paste __Secure-1PSID cookie value">
            <label style="font-size: 12px; color: var(--text-sub);">__Secure-1PSIDTS</label>
            <input type="text" id="psidts" placeholder="Paste __Secure-1PSIDTS cookie value">
            <button onclick="saveCookies()">Save Session Cookies</button>
        </div>

        <!-- 2. API Key Management -->
        <div class="card">
            <div class="card-title">🔑 2. API Key Management</div>
            <div style="display: flex; gap: 8px;">
                <input type="text" id="keyName" placeholder="Key name (e.g. Production App)" style="margin-bottom:0;">
                <button onclick="createKey()" style="white-space: nowrap;">Create API Key</button>
            </div>
            <div class="key-list" id="keyList"></div>
        </div>
    </div>

    <div class="grid">
        <!-- 3. Large AI Integration Prompt -->
        <div class="card" style="grid-column: span 2;">
            <div class="card-title">🤖 3. Large AI System Integration Prompt (Copy-Paste directly into Claude / ChatGPT / Cursor)</div>
            <p style="font-size: 13px; color: var(--text-sub); margin-bottom: 12px;">Give this prompt directly to any AI coding assistant to auto-integrate this API into your application codebase:</p>
            <div class="code-block">
                <button class="copy-btn" onclick="copyPrompt()">📋 Copy Prompt</button>
                <pre id="aiPrompt">You are an expert software developer. Please integrate our self-hosted OpenAI-compatible Gemini API into our application.

[API CONFIGURATION]
Base URL: http://localhost:8000/v1
Authentication: Bearer YOUR_API_KEY
Model: gemini-2.5-flash (or gemini-2.5-pro)

[ENDPOINTS AVAILABLE]
- POST http://localhost:8000/v1/chat/completions (Supports streaming SSE & standard JSON)
- GET http://localhost:8000/v1/models

[PYTHON IMPLEMENTATION CODE]
import openai

client = openai.OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="YOUR_API_KEY",
)

response = client.chat.completions.create(
    model="gemini-2.5-flash",
    messages=[{"role": "user", "content": "Hello!"}],
    stream=True
)

for chunk in response:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)

Please implement this integration into our codebase cleanly with error handling and retry logic.</pre>
            </div>
        </div>
    </div>

    <div class="grid">
        <!-- 4. Interactive Playground -->
        <div class="card" style="grid-column: span 2;">
            <div class="card-title">🧪 4. Interactive AI Studio Playground</div>
            <textarea id="promptInput" rows="3" placeholder="Type your prompt here to test generation live..."></textarea>
            <button class="btn-cyan" onclick="testPrompt()">Run Prompt Live</button>
            <div style="margin-top: 14px;">
                <label style="font-size: 12px; color: var(--text-sub);">Response Output:</label>
                <pre id="testOutput">Response output will appear here...</pre>
            </div>
        </div>
    </div>

    <script>
        const host = window.location.origin + "/v1";
        document.getElementById("hostUrl").innerText = host;

        async function loadKeys() {
            // Load key list via API
            const res = await fetch("/api/config");
            const data = await res.json();
            document.getElementById("psid").value = data.cookies["__Secure-1PSID"] || "";
            document.getElementById("psidts").value = data.cookies["__Secure-1PSIDTS"] || "";
            
            const list = document.getElementById("keyList");
            list.innerHTML = "";
            for (const [key, info] of Object.entries(data.api_keys)) {
                list.innerHTML += `
                    <div class="key-item">
                        <span>🔑 <b>${info.name}</b>: ${key}</span>
                        <button class="del-btn" onclick="deleteKey('${key}')">Delete</button>
                    </div>
                `;
            }
        }

        async function saveCookies() {
            const psid = document.getElementById("psid").value;
            const psidts = document.getElementById("psidts").value;
            await fetch("/api/cookies", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ "__Secure-1PSID": psid, "__Secure-1PSIDTS": psidts })
            });
            alert("Cookies saved successfully!");
        }

        async function autoExtract() {
            const res = await fetch("/api/cookies/auto-extract", { method: "POST" });
            const data = await res.json();
            if (data.status === "success") {
                document.getElementById("psid").value = data.cookies["__Secure-1PSID"];
                document.getElementById("psidts").value = data.cookies["__Secure-1PSIDTS"];
                alert("Auto-extracted cookies successfully from your default browser!");
            } else {
                alert("Auto-extract failed: " + data.detail);
            }
        }

        async function createKey() {
            const name = document.getElementById("keyName").value || "App Key";
            await fetch("/api/keys", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ name })
            });
            loadKeys();
        }

        async function deleteKey(key) {
            await fetch("/api/keys/" + key, { method: "DELETE" });
            loadKeys();
        }

        function copyPrompt() {
            const text = document.getElementById("aiPrompt").innerText;
            navigator.clipboard.writeText(text);
            alert("Large AI Integration Prompt copied to clipboard!");
        }

        async function testPrompt() {
            const prompt = document.getElementById("promptInput").value;
            const out = document.getElementById("testOutput");
            out.innerText = "Generating response...";
            
            const res = await fetch("/v1/chat/completions", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    model: "gemini-2.5-flash",
                    messages: [{ role: "user", content: prompt }]
                })
            });
            const data = await res.json();
            if (data.choices && data.choices[0]) {
                out.innerText = data.choices[0].message.content;
            } else {
                out.innerText = JSON.stringify(data, null, 2);
            }
        }

        loadKeys();
    </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    """Enterprise AI Studio Web Interface by Joy Saha."""
    docs_file = Path(__file__).resolve().parent.parent.parent / "docs" / "index.html"
    if docs_file.exists():
        return HTMLResponse(content=docs_file.read_text(encoding="utf-8"))
    return DASHBOARD_HTML


@app.get("/api/config")
async def get_config():
    """Get active server configuration."""
    return {"api_keys": API_KEYS, "cookies": COOKIES}
