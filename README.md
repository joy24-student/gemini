<div align="center">

# 🤖 Gemini Unofficial Client API

**A production-grade, enterprise-ready Python & JavaScript client for Google Gemini Web UI — Zero API Key Required.**

[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue?style=for-the-badge&logo=python)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)
[![HTTP/2](https://img.shields.io/badge/HTTP%2F2-Enabled-blueviolet?style=for-the-badge)](https://httpx.readthedocs.io/)
[![FastAPI](https://img.shields.io/badge/FastAPI-OpenAI--Compatible-teal?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com/)
[![Prometheus](https://img.shields.io/badge/Observability-Prometheus-orange?style=for-the-badge&logo=prometheus)](https://prometheus.io/)

> Operates entirely via browser session cookies (`__Secure-1PSID` / `__Secure-1PSIDTS`).  
> Fully unofficial — reverse-engineered from the Gemini Web UI RPC protocol.

</div>

---

## 📋 Table of Contents

1. [Overview & Key Features](#-overview--key-features)
2. [Architecture Overview](#-architecture-overview)
3. [Project Structure](#-project-structure)
4. [Installation](#-installation)
5. [Authentication Setup](#-authentication-setup)
6. [Quick Start](#-quick-start)
7. [Core API Reference](#-core-api-reference)
8. [Available Models](#-available-models)
9. [Memory & Multi-Turn Conversations](#-memory--multi-turn-conversations)
10. [High-Scale Concurrency Engine](#-high-scale-concurrency-engine-500-users)
11. [Real-Time Live Engines](#-real-time-live-engines)
12. [OpenAI-Compatible REST API Server](#-openai-compatible-rest-api-server)
13. [Multimodal: Image & File Uploads](#-multimodal-image--file-uploads)
14. [Observability & Health Monitoring](#-observability--health-monitoring)
15. [JavaScript / Node.js Client](#-javascript--nodejs-client)
16. [VPS Deployment Guide](#-vps-deployment-guide-ubuntudebian)
17. [Vercel Deployment Guide](#-vercel-deployment-guide)
18. [Environment Variables Reference](#-environment-variables-reference)
19. [Performance Benchmarks](#-performance-benchmarks)
20. [Security Best Practices](#-security-best-practices)
21. [Troubleshooting](#-troubleshooting)
22. [Contributing](#-contributing)
23. [License](#-license)

---

## 🚀 Overview & Key Features

The **Gemini Unofficial Client API** reverse-engineers Google Gemini's internal Web UI `StreamGenerate` RPC protocol, providing a complete Python SDK and self-hosted REST API server with **zero dependency on paid Google AI Studio API keys**.

### ✅ Core Capabilities

| Feature | Description |
|---|---|
| **Zero API Key** | Uses browser session cookies — no paid credentials needed |
| **Auto Cookie Extraction** | Auto-extracts cookies from Chrome, Edge, Firefox, and Brave |
| **HTTP/2 + Async** | `httpx.AsyncClient` with HTTP/2 multiplexing & connection pooling |
| **Real-Time Streaming** | `ask_stream()` yields text chunks as they arrive |
| **Multimodal Input** | Send images (PNG, JPG, WebP) directly to Gemini Vision |
| **Official SDK Response** | `response.text`, `.candidates`, `.usage_metadata`, `.parts` |
| **Conversation Memory** | Named sessions with persistent JSON history |
| **Multi-User Scale** | `HighScaleSupportEngine` — 500+ concurrent users, LRU cache |
| **Live Voice Pipeline** | Sub-200ms latency with sentence-pipelined TTS audio |
| **WebSocket Bridge** | Local `ws://` server compatible with official Gemini Live SDK |
| **OpenAI-Compatible REST** | Drop-in `POST /v1/chat/completions` with SSE streaming |
| **Prometheus Metrics** | `/metrics`, `/health/live`, `/health/ready` endpoints |
| **Multi-Lingual TTS** | Auto-detects Bengali, switches voice (`bn-BD-NabanitaNeural`) |
| **Browser Impersonation** | `curl_cffi` Chrome 110 TLS fingerprinting |
| **Protocol Drift Detection** | Structural schema fingerprinting alerts on RPC changes |

---

## 🏗 Architecture Overview

```
┌────────────────────────────────────────────────────────────────────────┐
│                    GEMINI UNOFFICIAL CLIENT API                        │
│                        (gemini_client package)                         │
└────────────────────────────────────────────────────────────────────────┘
                                     │
          ┌──────────────────────────┼──────────────────────────┐
          ▼                          ▼                          ▼
┌──────────────────┐    ┌───────────────────────┐    ┌──────────────────────┐
│  Python SDK      │    │  FastAPI REST Server  │    │  Node.js Client      │
│  (gemini_client) │    │  (server/app.py)      │    │  (gemini.js)         │
└──────────────────┘    └───────────────────────┘    └──────────────────────┘
         │                          │
┌────────┴───────────────┐  ┌───────┴──────────────────────────────────────┐
│   Core Engine          │  │   API Endpoints                              │
│   core.py              │  │   POST /v1/chat/completions (OpenAI compat)  │
│   ├─ AsyncChatbot      │  │   GET  /                   (AI Studio UI)    │
│   ├─ Chatbot (sync)    │  │   GET  /health/live                          │
│   └─ _ask_once()       │  │   GET  /health/ready                         │
│                        │  │   GET  /metrics            (Prometheus)      │
│   schema.py            │  │   POST /api/keys/generate                    │
│   ├─ extract_response  │  └──────────────────────────────────────────────┘
│   ├─ _walk_for_text    │
│   └─ ProtocolMonitor   │
│                        │
│   cookie_manager.py    │
│   └─ CookieExtractor   │   ← Chrome/Edge/Firefox/Brave auto-extract
│                        │
│   memory.py            │
│   ├─ ConversationMemory│   ← Named sessions, history, system prompts
│   └─ MultiUserManager  │   ← Per-user isolated sessions
│                        │
│   scale_engine.py      │
│   ├─ HighScaleEngine   │   ← 500+ concurrent users
│   ├─ AsyncSessionPool  │   ← Worker pool with per-user async locks
│   └─ HighScaleMemPool  │   ← LRU RAM cache + disk eviction
│                        │
│   unofficial_live/     │
│   ├─ pipeline_session  │   ← Sentence-pipelined TTS (<200ms latency)
│   ├─ websocket_live    │   ← Official Gemini Live WebSocket bridge
│   └─ playwright_session│   ← Headless Chromium background engine
│                        │
│   tts.py               │   ← Edge TTS + SAPI fallback + auto language detect
│   retry.py             │   ← Full-jitter backoff, Retry-After support
│   observability.py     │   ← Prometheus metrics, liveness/readiness probes
└────────────────────────┘
                │
                ▼
┌────────────────────────────────────────────────────────────┐
│                    Google Gemini Web UI                    │
│    POST StreamGenerate → BardFrontendService RPC           │
│    Outer JSON: wrb.fr envelope                             │
│    Inner JSON: candidates, conversation_id, response_id    │
└────────────────────────────────────────────────────────────┘
```

### Request Flow (Single Ask)

```
User Code
  │
  │ bot.ask("Hello")
  ▼
Chatbot (sync wrapper)
  │
  │ asyncio.run_coroutine_threadsafe(...)
  ▼
AsyncChatbot._ask_once()
  │
  ├─ Build f.req payload + SNlM0e CSRF token
  ├─ POST StreamGenerate (HTTP/2, curl_cffi Chrome impersonation)
  │
  ▼
Google StreamGenerate RPC  →  chunked wrb.fr JSON response
  │
  ├─ parse lines → find "wrb.fr" envelope
  ├─ schema.extract_response() → ParsedResponse
  ├─ _walk_for_text() fallback walker (if schema drift)
  ├─ ProtocolMonitor.record() → check fingerprint drift
  │
  ▼
GenerateContentResponse(text=..., candidates=..., usage_metadata=...)
```

---

## 📁 Project Structure

```
Gemini-Chat-API/
│
├── gemini_client/                    # Main Python package
│   ├── __init__.py                   # Public exports
│   ├── core.py                       # AsyncChatbot & Chatbot engine (~940 lines)
│   ├── schema.py                     # Adaptive response schema walker
│   ├── enums.py                      # Model & endpoint definitions
│   ├── response.py                   # GenerateContentResponse (official SDK compat)
│   ├── memory.py                     # ConversationMemory & MultiUserMemoryManager
│   ├── scale_engine.py               # HighScaleSupportEngine (500+ users)
│   ├── cookie_manager.py             # Browser cookie auto-extractor
│   ├── cookie_pool.py                # Cookie pool with health checking
│   ├── images.py                     # WebImage & GeneratedImage extractors
│   ├── utils.py                      # load_cookies(), upload_file()
│   ├── tts.py                        # TTSEngine: Edge TTS + SAPI fallback
│   ├── retry.py                      # Full-jitter retry with Retry-After support
│   ├── observability.py              # Prometheus metrics + health routes
│   ├── sync_bridge.py                # SyncStreamBridge for sync streaming
│   ├── dedup.py                      # Response deduplication
│   ├── constants.py                  # Shared constants
│   │
│   ├── server/                       # Self-hosted API server
│   │   ├── __init__.py
│   │   └── app.py                    # FastAPI: Web dashboard + OpenAI REST API
│   │
│   └── unofficial_live/              # Real-time live conversation engines
│       ├── __init__.py
│       ├── pipeline_session.py       # PipelineLiveSession: sentence-pipelined TTS
│       ├── websocket_live.py         # UnofficialLiveWebSocket + BridgeServer
│       ├── playwright_session.py     # PlaywrightLiveSession: headless Chromium
│       └── official_adapter.py       # Official Gemini Live protocol adapter
│
├── examples/                         # Usage examples
│   ├── unofficial_chat.py
│   ├── streaming_chat.py
│   ├── unofficial_image_chat.py
│   ├── memory_chat_demo.py
│   ├── interactive_terminal_chat.py
│   ├── unofficial_live_conversation.py
│   ├── unofficial_live_websocket.py
│   ├── high_scale_500_users_demo.py
│   └── support_center_api.py
│
├── gemini.js                         # Node.js / JavaScript client
├── server.py                         # Entry point: uvicorn server launcher
├── terminal_chat.py                  # Interactive terminal chat UI
├── voice_talk.py                     # Voice conversation demo
├── requirements.txt                  # Python dependencies
├── setup.py                          # Package setup
├── cookies.json                      # Cookie file (gitignored)
└── README.md
```

---

## 📦 Installation

### Prerequisites

- **Python** ≥ 3.10
- **pip** ≥ 22.0
- A Google account logged into Gemini at [gemini.google.com](https://gemini.google.com)

### Install from Source

```bash
git clone https://github.com/OEvortex/Gemini-Chat-API.git
cd Gemini-Chat-API
pip install -r requirements.txt
```

### Install as Package

```bash
pip install -e .
```

### Full Dependencies

```bash
# Core (required)
pip install curl_cffi>=0.7.0 httpx[http2]>=0.27.0 requests>=2.31.0 pydantic>=2.0
pip install rich>=13.0 orjson>=3.9.0 browser-cookie3>=0.20.1

# REST API Server
pip install fastapi>=0.111.0 uvicorn[standard]>=0.30.0

# Observability
pip install prometheus-client>=0.20.0

# Real-Time Voice Pipeline
pip install edge-tts>=6.1.9 websockets>=12.0

# OR install everything at once:
pip install -r requirements.txt
```

### Optional: Live Voice Playback

```bash
# Windows
pip install pipwin && pipwin install pyaudio

# Linux
sudo apt install python3-pyaudio

# macOS
brew install portaudio && pip install pyaudio
```

### Optional: Playwright Headless Engine

```bash
pip install playwright
playwright install chromium
```

---

## 🔐 Authentication Setup

Gemini Web UI requires two session cookies for authentication:

| Cookie | Purpose |
|---|---|
| `__Secure-1PSID` | Main Google session identifier |
| `__Secure-1PSIDTS` | Rotating anti-replay timestamp token |

### Method 1: Automatic Browser Extraction (Recommended)

The library automatically finds and decrypts cookies from your locally installed browser:

```python
from gemini_client import Chatbot, Model

# Auto-extracts cookies from Chrome/Edge/Firefox/Brave
bot = Chatbot(auto_cookie=True, model=Model.G_2_5_FLASH)
response = bot.ask("Hello!")
print(response.text)
```

Supported browsers:
- Google Chrome
- Microsoft Edge
- Firefox
- Brave

> **Platform Note**: On Windows, DPAPI decryption is used. On macOS, Keychain is used. On Linux, SecretService/KWallet.

### Method 2: Manual Cookie File (`cookies.json`)

1. Open [https://gemini.google.com/app](https://gemini.google.com/app) in your browser.
2. Open DevTools (`F12`) → **Application** → **Cookies** → `https://gemini.google.com`.
3. Copy the values of `__Secure-1PSID` and `__Secure-1PSIDTS`.
4. Create `cookies.json`:

```json
[
    {
        "name": "__Secure-1PSID",
        "value": "YOUR___SECURE-1PSID_VALUE_HERE"
    },
    {
        "name": "__Secure-1PSIDTS",
        "value": "YOUR___SECURE-1PSIDTS_VALUE_HERE"
    }
]
```

```python
from gemini_client import Chatbot

bot = Chatbot(cookie_path="cookies.json")
response = bot.ask("Hello!")
print(response.text)
```

### Method 3: Direct Cookie Strings

```python
from gemini_client import AsyncChatbot, Model
import asyncio

async def main():
    bot = await AsyncChatbot.create(
        secure_1psid="your_1psid_value",
        secure_1psidts="your_1psidts_value",
        model=Model.G_2_5_FLASH
    )
    response = await bot.ask("Hello!")
    print(response.text)

asyncio.run(main())
```

> **Security Warning**: Never commit `cookies.json` to version control. Add it to `.gitignore`.

---

## ⚡ Quick Start

### Synchronous Chat

```python
from gemini_client import Chatbot, Model

bot = Chatbot(cookie_path="cookies.json", model=Model.G_2_5_FLASH)

response = bot.ask("Explain quantum entanglement in simple terms.")
print(response.text)
print(f"Tokens used: {response.usage_metadata.total_token_count}")
```

### Real-Time Streaming

```python
from gemini_client import Chatbot

bot = Chatbot(cookie_path="cookies.json")

print("Gemini: ", end="", flush=True)
for chunk in bot.ask_stream("Write a haiku about the ocean."):
    print(chunk, end="", flush=True)
print()
```

### Async Usage

```python
import asyncio
from gemini_client import AsyncChatbot, Model

async def main():
    bot = await AsyncChatbot.create(
        "YOUR_1PSID",
        "YOUR_1PSIDTS",
        model=Model.G_2_5_FLASH
    )
    response = await bot.ask("What is the capital of Bangladesh?")
    print(response.text)

    # Async streaming
    async for chunk in bot.ask_stream("Count from 1 to 5 slowly."):
        print(chunk, end="", flush=True)

asyncio.run(main())
```

---

## 📚 Core API Reference

### `Chatbot` (Synchronous)

```python
Chatbot(
    cookie_path: str = None,       # Path to cookies.json
    auto_cookie: bool = False,     # Auto-extract from browser
    proxy: str | dict = None,      # Proxy URL or dict
    timeout: int = 20,             # Request timeout in seconds
    model: Model = Model.UNSPECIFIED,  # Gemini model to use
    impersonate: str = "chrome110",    # Browser fingerprint
    session_name: str = None,      # Named memory session to auto-load
    system_instruction: str = None,# System prompt text
    memory: ConversationMemory = None, # Custom memory manager
)
```

| Method | Signature | Description |
|---|---|---|
| `ask` | `ask(message, image=None, retry=3) → GenerateContentResponse` | Send a single message, returns full response |
| `ask_stream` | `ask_stream(message, image=None) → Iterator[str]` | Stream response chunks as they arrive |
| `save_conversation` | `save_conversation(file_path, name)` | Persist conversation state to JSON |
| `load_conversation` | `load_conversation(file_path, name)` | Load prior conversation state |

### `AsyncChatbot` (Asynchronous)

```python
bot = await AsyncChatbot.create(
    secure_1psid: str,
    secure_1psidts: str,
    proxy: dict = None,
    timeout: int = 20,
    model: Model = Model.UNSPECIFIED,
    impersonate: str = "chrome110",
    session_name: str = None,
    system_instruction: str = None,
    memory: ConversationMemory = None,
)
```

| Method | Signature | Description |
|---|---|---|
| `ask` | `await ask(message, image=None, retry=3) → GenerateContentResponse` | Async single-turn query |
| `ask_stream` | `async for chunk in ask_stream(message, image=None)` | Async streaming generator |
| `save_conversation` | `await save_conversation(file_path, name)` | Async conversation save |
| `load_conversation` | `await load_conversation(file_path, name)` | Async conversation load |

### `GenerateContentResponse`

```python
response = bot.ask("Hello")

response.text                          # str: Full response text
response.candidates                    # List[Candidate]: Generated candidates
response.usage_metadata.total_token_count   # int: Token count
response.usage_metadata.prompt_token_count  # int: Input tokens
response.images                        # List[dict]: Extracted image URLs
response.error                         # bool: True if request failed
response.error_message                 # str | None: Error details

# Dict-style backward compatibility
response["content"]                    # Same as response.text
response["conversation_id"]            # Session conversation ID
response["images"]                     # Image URLs list

# Candidates
candidate = response.candidates[0]
candidate.text                         # str: Candidate text
candidate.finish_reason                # str: "STOP"
candidate.index                        # int
candidate.token_count                  # int

# Content parts
for part in candidate.content.parts:
    print(part.text)
```

---

## 🤖 Available Models

| Model Enum | Model Name | Notes |
|---|---|---|
| `Model.G_2_5_FLASH` | `gemini-2.5-flash` | Fast, general-purpose (default) |
| `Model.G_2_5_PRO` | `gemini-2.5-pro` | More capable, slower |
| `Model.G_2_0_FLASH` | `gemini-2.0-flash` | Previous generation |
| `Model.G_2_0_FLASH_THINKING` | `gemini-2.0-flash-thinking` | Reasoning mode |
| `Model.GEMINI_3_0_PRO` | `gemini-3.0-pro` | Latest generation Pro |
| `Model.GEMINI_3_0_FLASH` | `gemini-3.0-flash` | Latest generation Flash |
| `Model.GEMINI_3_0_FLASH_THINKING` | `gemini-3.0-flash-thinking` | Latest + thinking |
| `Model.G_2_0_EXP_ADVANCED` | `gemini-2.0-exp-advanced` | Advanced users only |
| `Model.G_2_5_EXP_ADVANCED` | `gemini-2.5-exp-advanced` | Advanced users only |
| `Model.UNSPECIFIED` | (default) | No model header override |

```python
from gemini_client import Chatbot, Model

# By enum
bot = Chatbot(cookie_path="cookies.json", model=Model.G_2_5_PRO)

# By name string
model = Model.from_name("gemini-2.5-flash")
```

---

## 🧠 Memory & Multi-Turn Conversations

### Named Session Memory

```python
from gemini_client import Chatbot, ConversationMemory, Model

# Create a named memory session
memory = ConversationMemory(
    session_name="my_coding_assistant",
    max_messages=50,
    system_instruction="You are an expert Python developer. Be concise."
)

bot = Chatbot(cookie_path="cookies.json", memory=memory)

# First session
r1 = bot.ask("My name is Joy and I'm learning FastAPI.")
print(r1.text)

# Save to disk
memory.save("my_coding_assistant")

# Later — restore and continue
memory2 = ConversationMemory(session_name="my_coding_assistant")
memory2.load("my_coding_assistant")
bot2 = Chatbot(cookie_path="cookies.json", memory=memory2)
r2 = bot2.ask("What was I learning?")  # "You were learning FastAPI, Joy!"
print(r2.text)
```

### Inspect History

```python
for msg in memory.get_history():
    print(f"[{msg.role}] {msg.text[:80]}...")

# Get formatted context prompt
context = memory.get_context_prompt()
print(context)
```

### Multi-User Memory Manager (Support Center)

```python
from gemini_client import MultiUserMemoryManager

manager = MultiUserMemoryManager(
    max_messages_per_user=30,
    storage_dir="./user_sessions"
)

# Per-user isolated sessions
manager.add_message("user_123", role="user", text="Hello, I need help.")
manager.add_message("user_456", role="user", text="Track my order #999.")

# Retrieve history for a specific user
history = manager.get_history("user_123")
```

---

## ⚡ High-Scale Concurrency Engine (500+ Users)

The `HighScaleSupportEngine` is designed for concurrent multi-user server deployments.

### Architecture

- **`AsyncSessionPool`**: Pool of `AsyncChatbot` workers with round-robin distribution
- **`HighScaleMemoryPool`**: LRU cache (200 users in RAM) + automatic disk eviction via `orjson`
- **Per-user `asyncio.Lock`**: Serializes concurrent requests from the same user
- **`asyncio.Semaphore(500)`**: Global concurrency throttle
- **Background Health Check**: Auto-refreshes cookies/tokens

### Usage

```python
import asyncio
from gemini_client import HighScaleSupportEngine, Model

async def main():
    engine = HighScaleSupportEngine(
        cookie_path="cookies.json",
        model=Model.G_2_5_FLASH,
        pool_size=4,                  # Number of AsyncChatbot workers
        max_ram_users=200,            # LRU memory cache size
        max_history_per_user=30,      # Messages per user
        system_instruction="You are a helpful customer support agent.",
        storage_dir="./sessions"      # Disk session storage
    )

    await engine.initialize()

    # Concurrent user requests — each gets isolated session
    async def user_query(user_id: str, message: str):
        response = await engine.ask(user_id, message)
        print(f"[{user_id}] {response.text[:100]}")

    # Simulate 10 concurrent users
    await asyncio.gather(*[
        user_query(f"user_{i}", "What are your business hours?")
        for i in range(10)
    ])

    await engine.close()

asyncio.run(main())
```

### Support Center API Pattern

```python
# examples/support_center_api.py
from fastapi import FastAPI
from gemini_client import HighScaleSupportEngine

app = FastAPI()
engine = HighScaleSupportEngine(cookie_path="cookies.json")

@app.on_event("startup")
async def startup():
    await engine.initialize()

@app.post("/chat/{user_id}")
async def chat(user_id: str, message: str):
    response = await engine.ask(user_id, message)
    return {"reply": response.text}
```

---

## 🎙 Real-Time Live Engines

### 1. Sentence-Pipelined Voice Engine

Sub-200ms first-audio latency via concurrent sentence buffering + TTS synthesis.

```python
import asyncio
from gemini_client import Chatbot, UnofficialLiveChatbot
from gemini_client.unofficial_live.pipeline_session import PipelineLiveSession

async def main():
    from gemini_client import AsyncChatbot
    from gemini_client.utils import load_cookies

    psid, psidts = load_cookies("cookies.json")
    bot = await AsyncChatbot.create(psid, psidts)

    session = PipelineLiveSession(
        chatbot=bot,
        voice_name="en-US-AvaNeural",    # Microsoft Edge TTS voice
        enable_playback=True              # Auto-play audio through speakers
    )

    response_text = await session.send_voice_prompt(
        "Explain the water cycle in three sentences."
    )
    print("Gemini said:", response_text)

asyncio.run(main())
```

**How it works:**
1. User prompt is sent via `AsyncChatbot.ask_stream()`
2. Regex sentence detector (`[.!?\n]+`) buffers streaming tokens
3. On sentence boundary: immediately dispatch TTS synthesis for Sentence N
4. While Sentence N is playing, Gemini is still generating Sentence N+1
5. `UnofficialSpeakerStream` queues PCM audio chunks without blocking

### 2. Official WebSocket Bridge Server

Runs `ws://127.0.0.1:9000` — any client built for the official Gemini Live API connects with **zero API keys**.

```python
import asyncio
from gemini_client import Chatbot, UnofficialLiveBridgeServer

async def main():
    bot = Chatbot(cookie_path="cookies.json")
    server = UnofficialLiveBridgeServer(
        chatbot=bot,
        host="127.0.0.1",
        port=9000,
        voice_name="en-US-AvaNeural"
    )
    print("Bridge running on ws://127.0.0.1:9000")
    await server.start()

asyncio.run(main())
```

Connect any official Gemini Live WebSocket client to `ws://127.0.0.1:9000`.  
Receives `BidiGenerateContentServerContent` JSON frames with:
- `modelTurn.parts[].text` — text delta
- `modelTurn.parts[].inlineData` — `audio/pcm;rate=24000` base64 audio

### 3. UnofficialLiveWebSocket (Direct Client)

```python
import asyncio
from gemini_client import Chatbot, UnofficialLiveWebSocket

async def main():
    bot = Chatbot(cookie_path="cookies.json")
    ws = UnofficialLiveWebSocket(bot, voice_name="en-US-AvaNeural")

    async for event in ws.stream("Tell me about space exploration."):
        if event["type"] == "text":
            print(event["text"], end="", flush=True)
        elif event["type"] == "audio":
            # PCM audio at 24000 Hz — play with PyAudio
            pass

asyncio.run(main())
```

### 4. Playwright Headless Engine

Automates a real Chromium browser silently in the background for maximum compatibility.

```python
from gemini_client.unofficial_live.playwright_session import PlaywrightLiveSession
from gemini_client.utils import load_cookies
import asyncio

async def main():
    psid, psidts = load_cookies("cookies.json")
    session = PlaywrightLiveSession(
        secure_1psid=psid,
        secure_1psidts=psidts
    )
    await session.start()
    response = await session.send("What is the meaning of life?")
    print(response)
    await session.close()

asyncio.run(main())
```

### Multi-Lingual TTS (Auto Language Detection)

The TTS engine automatically detects the language of the Gemini response and switches voices:

| Language Detected | Voice Used |
|---|---|
| English (default) | `en-US-AvaNeural` |
| Bengali (বাংলা) | `bn-BD-NabanitaNeural` |

---

## 🌐 OpenAI-Compatible REST API Server

The built-in FastAPI server provides:
- **AI Studio Web Dashboard** (`GET /`) — Dark-mode UI to manage cookies, API keys, test prompts
- **OpenAI-Compatible API** (`POST /v1/chat/completions`) — SSE streaming + non-streaming
- **API Key Management** — Generate `sk-gemini-...` keys for client authentication
- **Prometheus Metrics** (`GET /metrics`)
- **Health Probes** (`GET /health/live`, `GET /health/ready`)

### Starting the Server

```bash
python server.py --host 0.0.0.0 --port 8000
```

Output:
```
═══════════════════════════════════════════════════════════════════
  ⚡ Gemini Unofficial AI Studio Web Dashboard & API Server
═══════════════════════════════════════════════════════════════════
  🌐 AI Studio Web Dashboard:  http://localhost:8000
  🔗 OpenAI Base URL:           http://localhost:8000/v1
  📖 Interactive API Docs:     http://localhost:8000/docs
═══════════════════════════════════════════════════════════════════
```

### Using with the OpenAI Python SDK

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="sk-gemini-YOUR_KEY_HERE"   # From the AI Studio dashboard
)

# Non-streaming
response = client.chat.completions.create(
    model="gemini-2.5-flash",
    messages=[{"role": "user", "content": "Hello, Gemini!"}]
)
print(response.choices[0].message.content)

# Streaming
stream = client.chat.completions.create(
    model="gemini-2.5-flash",
    messages=[{"role": "user", "content": "Count from 1 to 10."}],
    stream=True
)
for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
```

### REST API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | AI Studio Web Dashboard (HTML UI) |
| `POST` | `/v1/chat/completions` | OpenAI-compatible chat (streaming + non-streaming) |
| `GET` | `/v1/models` | List available models |
| `POST` | `/api/cookies/set` | Set authentication cookies |
| `POST` | `/api/keys/generate` | Generate new API key |
| `GET` | `/api/keys` | List all API keys |
| `DELETE` | `/api/keys/{key}` | Revoke an API key |
| `GET` | `/health/live` | Liveness probe (always 200 if process running) |
| `GET` | `/health/ready` | Readiness probe (checks cookie pool health) |
| `GET` | `/metrics` | Prometheus metrics in text format |
| `GET` | `/docs` | Interactive Swagger API documentation |

### Request Format

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-gemini-YOUR_KEY" \
  -d '{
    "model": "gemini-2.5-flash",
    "messages": [
      {"role": "user", "content": "What is 2 + 2?"}
    ],
    "stream": false
  }'
```

---

## 🖼 Multimodal: Image & File Uploads

```python
from gemini_client import Chatbot

bot = Chatbot(cookie_path="cookies.json")

# Analyze a local image file
response = bot.ask(
    "Describe in detail what you see in this image.",
    image="photo.jpg"         # PNG, JPG, WebP supported
)
print(response.text)

# Analyze from bytes
with open("diagram.png", "rb") as f:
    image_bytes = f.read()

response = bot.ask("Explain this system architecture diagram.", image=image_bytes)
print(response.text)
```

### How Image Upload Works

1. `upload_file()` reads the image bytes from path or bytes input
2. POSTs to Google's push upload server: `https://content-push.googleapis.com/upload/`
3. Receives an upload ID: `/contrib_service/ttl_1d/...`
4. Embeds the upload ID in the `StreamGenerate` `f.req` payload:
   `[[message], [[[upload_id, 1]]], [conv_id, resp_id, choice_id]]`

### Extract Images from Responses

```python
response = bot.ask("Show me some beautiful landscape images.")

# Web images returned by Gemini
for img in response.images:
    print(img["url"])    # Direct image URL
    print(img["title"])  # Image title/caption
    print(img["alt"])    # Alt text
```

---

## 📊 Observability & Health Monitoring

### Prometheus Metrics

The server exposes standard Prometheus metrics at `GET /metrics`:

| Metric | Type | Labels | Description |
|---|---|---|---|
| `gemini_requests_total` | Counter | `model`, `status` | Total API requests |
| `gemini_request_latency_seconds` | Histogram | `model` | Request latency distribution |
| `gemini_active_sessions` | Gauge | — | Current active user sessions |
| `gemini_cookie_pool_healthy` | Gauge | — | Healthy cookies in pool |
| `gemini_cookie_pool_total` | Gauge | — | Total cookies in pool |

```python
from gemini_client.observability import Metrics, add_health_routes

metrics = Metrics()
add_health_routes(app, metrics)

# Record a request
metrics.record_request(model="gemini-2.5-flash", status="ok", latency=0.42)
metrics.set_active_sessions(12)
metrics.set_cookie_pool(healthy=3, total=5)
```

### Health Endpoints

```bash
# Liveness — is the process running?
curl http://localhost:8000/health/live
# → {"status": "live"}

# Readiness — can it serve traffic?
curl http://localhost:8000/health/ready
# → {"status": "ready", "cookies": {"healthy": 1, "total": 1}}
```

### Grafana Dashboard Integration

Point your Prometheus scrape config at:
```yaml
scrape_configs:
  - job_name: 'gemini-unofficial'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: /metrics
```

---

## 🟨 JavaScript / Node.js Client

A standalone CommonJS client using `axios` for Node.js environments.

### Usage

```bash
node gemini.js
```

### Code Example

```javascript
const axios = require('axios');

const COOKIES = {
    '__Secure-1PSID': 'YOUR_1PSID',
    '__Secure-1PSIDTS': 'YOUR_1PSIDTS'
};

async function ask(message) {
    // See gemini.js for full implementation
    const response = await sendMessage(message, COOKIES);
    console.log('Gemini:', response.text);
    return response;
}

ask("What is the capital of Bangladesh?");
```

---

## 🖥 VPS Deployment Guide (Ubuntu/Debian)

### Step 1: Provision Your VPS

Recommended specs:
- **RAM**: ≥ 1 GB (2 GB+ for 500-user scale engine)
- **CPU**: 1–2 vCPUs
- **Storage**: 10 GB SSD
- **OS**: Ubuntu 22.04 LTS

### Step 2: Install System Dependencies

```bash
# Update and install prerequisites
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.11 python3.11-pip python3.11-venv git nginx

# Verify Python
python3.11 --version
```

### Step 3: Clone & Set Up the Project

```bash
# Clone the repository
git clone https://github.com/OEvortex/Gemini-Chat-API.git
cd Gemini-Chat-API

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
pip install fastapi uvicorn[standard] httpx
```

### Step 4: Configure Cookies

```bash
# Create cookies.json with your credentials
nano cookies.json
```

Paste:
```json
[
    {"name": "__Secure-1PSID", "value": "YOUR_1PSID_HERE"},
    {"name": "__Secure-1PSIDTS", "value": "YOUR_1PSIDTS_HERE"}
]
```

Secure the file:
```bash
chmod 600 cookies.json
```

### Step 5: Create a Systemd Service

```bash
sudo nano /etc/systemd/system/gemini-api.service
```

Paste:
```ini
[Unit]
Description=Gemini Unofficial API Server
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/Gemini-Chat-API
Environment=PATH=/home/ubuntu/Gemini-Chat-API/venv/bin
ExecStart=/home/ubuntu/Gemini-Chat-API/venv/bin/python server.py --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable gemini-api
sudo systemctl start gemini-api

# Check status
sudo systemctl status gemini-api
sudo journalctl -u gemini-api -f
```

### Step 6: Configure Nginx Reverse Proxy

```bash
sudo nano /etc/nginx/sites-available/gemini-api
```

Paste:
```nginx
server {
    listen 80;
    server_name YOUR_DOMAIN_OR_IP;

    # Increase buffer for SSE streaming
    proxy_buffering off;
    proxy_cache off;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE / Streaming support
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
        proxy_http_version 1.1;
        proxy_set_header Connection '';
        chunked_transfer_encoding on;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/gemini-api /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### Step 7: SSL with Let's Encrypt (Recommended)

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d YOUR_DOMAIN.com
sudo certbot renew --dry-run
```

### Step 8: Firewall Setup

```bash
sudo ufw allow 22
sudo ufw allow 80
sudo ufw allow 443
sudo ufw enable
```

### Verification

```bash
# Test the server
curl https://YOUR_DOMAIN.com/health/live
# → {"status": "live"}

curl https://YOUR_DOMAIN.com/health/ready
# → {"status": "ready", "cookies": {"healthy": 1, "total": 1}}
```

---

## ☁️ Vercel Deployment Guide

> **Note**: Vercel is designed for serverless functions and static sites. The full server with WebSocket and streaming works best on a VPS. For Vercel, deploy the REST API as serverless functions.

### Step 1: Install Vercel CLI

```bash
npm install -g vercel
```

### Step 2: Project Structure for Vercel

Create the following structure:

```
Gemini-Chat-API/
├── api/
│   ├── chat.py           # POST /api/chat
│   ├── health.py         # GET /api/health
│   └── stream.py         # GET /api/stream (SSE)
├── vercel.json
└── requirements.txt
```

### Step 3: Create Vercel API Handlers

**`api/chat.py`**:
```python
from http.server import BaseHTTPRequestHandler
import json
import os
from gemini_client import Chatbot, Model

def handler(request, response):
    if request.method == "POST":
        body = json.loads(request.body)
        message = body.get("message", "")

        bot = Chatbot(
            cookie_path=None,
            auto_cookie=False,
        )
        # Inject cookies from environment variables
        bot.async_chatbot.SNlM0e  # initialized via env vars

        resp = bot.ask(message)
        response.status_code = 200
        response.headers["Content-Type"] = "application/json"
        return json.dumps({"text": resp.text, "error": resp.error})
```

### Step 4: Configure `vercel.json`

```json
{
  "version": 2,
  "builds": [
    {
      "src": "api/*.py",
      "use": "@vercel/python"
    }
  ],
  "routes": [
    {
      "src": "/api/(.*)",
      "dest": "/api/$1"
    }
  ],
  "env": {
    "GEMINI_1PSID": "@gemini_1psid",
    "GEMINI_1PSIDTS": "@gemini_1psidts"
  },
  "functions": {
    "api/*.py": {
      "maxDuration": 60
    }
  }
}
```

### Step 5: Set Environment Variables

```bash
# Add secrets to Vercel
vercel secrets add gemini_1psid "YOUR_1PSID_VALUE"
vercel secrets add gemini_1psidts "YOUR_1PSIDTS_VALUE"
```

### Step 6: Deploy

```bash
vercel --prod
```

### Vercel Limitations & Workarounds

| Limitation | Impact | Workaround |
|---|---|---|
| 60s function timeout (Hobby) | Long Gemini responses may timeout | Upgrade to Pro (300s) or use VPS |
| No persistent file system | Cannot save `cookies.json` | Use environment variables for credentials |
| No WebSocket support | `UnofficialLiveBridgeServer` won't work | Use VPS for WebSocket features |
| Cold starts | First request ~2–3s slower | Use VPS or keep-warm pings |

> **Recommendation**: For production deployments with streaming, live voice, and WebSocket features, use a VPS with the systemd setup above. Vercel is suitable for simple REST API endpoints only.

---

## 🔧 Environment Variables Reference

| Variable | Description | Example |
|---|---|---|
| `GEMINI_1PSID` | `__Secure-1PSID` cookie value | `g.a000...` |
| `GEMINI_1PSIDTS` | `__Secure-1PSIDTS` cookie value | `g.a000...` |
| `GEMINI_MODEL` | Default model name | `gemini-2.5-flash` |
| `GEMINI_TIMEOUT` | Request timeout in seconds | `30` |
| `GEMINI_POOL_SIZE` | AsyncChatbot worker pool size | `4` |
| `GEMINI_MAX_USERS` | LRU cache max users (scale engine) | `200` |
| `GEMINI_STORAGE_DIR` | Session storage directory | `/data/sessions` |
| `GEMINI_SYSTEM_PROMPT` | Default system instruction | `You are a helpful assistant.` |

---

## 📈 Performance Benchmarks

| Optimization | Method | Benefit |
|---|---|---|
| **HTTP/2 Multiplexing** | `httpx.AsyncClient(http2=True)` | Eliminates TCP handshake per request |
| **Fast JSON Parsing** | `orjson` (stdlib `json` fallback) | 3x–5x faster payload serialization |
| **Regex Pre-compilation** | Module-level `re.compile()` | Zero regex recompilation overhead |
| **Lock-Protected Token Refresh** | `asyncio.Lock()` | Prevents thundering-herd on SNlM0e expiry |
| **Sentence TTS Pipelining** | Concurrent boundary detection | Sub-200ms first-audio latency |
| **LRU Memory Cache** | `OrderedDict` with eviction | O(1) session lookup, disk-evicts idle users |
| **Per-user Async Lock** | `asyncio.Lock` per `user_id` | Strict message ordering, no cross-user blocking |
| **Global Semaphore** | `asyncio.Semaphore(500)` | Hard concurrency cap, prevents overload |
| **Schema Fast-Path** | Known indices before walker | Millisecond response parsing |
| **orjson Disk I/O** | Binary JSON serialization | 2x faster session save/load |

### Throughput Estimates

| Configuration | Estimated Concurrent Users |
|---|---|
| Single `Chatbot` | 1 (synchronous) |
| Single `AsyncChatbot` | ~10–20 (async, no pool) |
| `HighScaleSupportEngine` (pool_size=4) | ~50–100 |
| `HighScaleSupportEngine` (pool_size=8) | ~200–500 |

---

## 🔒 Security Best Practices

> [!CAUTION]
> `__Secure-1PSID` grants **full access to your Google account session**. Treat it as a master password.

1. **Never commit `cookies.json`** — add to `.gitignore` immediately:
   ```
   cookies.json
   *.psid
   .env
   ```

2. **Use environment variables in production** — never hardcode credentials:
   ```bash
   export GEMINI_1PSID="your_value"
   export GEMINI_1PSIDTS="your_value"
   ```

3. **File permission hardening**:
   ```bash
   chmod 600 cookies.json    # Only owner can read
   chmod 700 .               # Restrict directory access
   ```

4. **API key authentication** — always require `sk-gemini-...` keys for the REST server:
   ```bash
   # Generate a key via the AI Studio dashboard
   curl http://localhost:8000/api/keys/generate -X POST
   ```

5. **Use HTTPS in production** — always deploy behind SSL (Let's Encrypt via Nginx).

6. **Rotate cookies periodically** — `__Secure-1PSIDTS` rotates automatically; run `CookieExtractor` weekly to refresh.

7. **Prometheus metric labels** — never include user IDs, conversation IDs, or cookie values in metric labels (already enforced in `observability.py`).

8. **Rate limiting** — add Nginx rate limiting to prevent abuse:
   ```nginx
   limit_req_zone $binary_remote_addr zone=gemini:10m rate=10r/s;
   limit_req zone=gemini burst=20 nodelay;
   ```

---

## 🔧 Troubleshooting

### `NameError: _walk_for_text`
**Cause**: Missing import in `core.py`.  
**Fix**: Ensure `_walk_for_text` is imported from `gemini_client.schema`:
```python
from gemini_client.schema import extract_response, ProtocolError, _monitor as _protocol_monitor, _walk_for_text
```

### `Response text is empty ('')`
**Cause**: Response parsing block incorrectly nested in exception handler (indentation bug).  
**Fix**: Verify `_ask_once()` in `core.py` — the `# Process response` block must be at the same indentation as the outer `try:` body, not inside the `except (HTTPError, ...)` block.

### `[WARNING] Protocol drift detected`
**Cause**: Google has silently changed the Web UI RPC schema (common after deployments).  
**Action**: The fallback `_walk_for_text` walker will handle it. If responses are wrong, update the fast-path indices in `schema.py:_extract_text_fast()`.

### Cookie Expired / `401 Unauthorized`
**Fix**: Re-extract cookies from your browser:
```python
from gemini_client.cookie_manager import CookieExtractor
extractor = CookieExtractor()
psid, psidts = extractor.extract()
```
Or manually copy fresh values from DevTools and update `cookies.json`.

### `ImportError: curl_cffi`
```bash
pip install curl_cffi --upgrade
# On Windows, may need:
pip install curl_cffi --no-binary curl_cffi
```

### Streaming Timeout on Vercel
**Cause**: Vercel Hobby plan has 60s function timeout; long Gemini responses exceed this.  
**Fix**: Upgrade to Vercel Pro (300s) or migrate to VPS deployment.

### `PyAudio` Installation Issues (Windows)
```bash
pip install pipwin
pipwin install pyaudio
```

### Build Label Updated Warning
```
[WARNING] Build label updated: boq_assistant-bard-web-server_... → boq_assistant-...
```
**This is informational only** — the client automatically updates its build label from the Gemini homepage. No action needed.

---

## 🗂 Examples Reference

| Example File | Description |
|---|---|
| [`examples/unofficial_chat.py`](examples/unofficial_chat.py) | Basic single-turn and multi-turn chat |
| [`examples/streaming_chat.py`](examples/streaming_chat.py) | Real-time streaming with typewriter effect |
| [`examples/unofficial_image_chat.py`](examples/unofficial_image_chat.py) | Multimodal image analysis |
| [`examples/memory_chat_demo.py`](examples/memory_chat_demo.py) | Named session memory, system instructions |
| [`examples/interactive_terminal_chat.py`](examples/interactive_terminal_chat.py) | Rich terminal UI interactive chat |
| [`examples/unofficial_live_conversation.py`](examples/unofficial_live_conversation.py) | Voice pipeline with audio playback |
| [`examples/unofficial_live_websocket.py`](examples/unofficial_live_websocket.py) | WebSocket bridge server demo |
| [`examples/high_scale_500_users_demo.py`](examples/high_scale_500_users_demo.py) | 500-user concurrent scale engine demo |
| [`examples/support_center_api.py`](examples/support_center_api.py) | Multi-user support center FastAPI integration |

---

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Install dev dependencies: `pip install -r requirements.txt`
4. Make your changes and write tests
5. Run the verification suite: `python full_system_verification.py`
6. Commit: `git commit -m "feat: add my feature"`
7. Push and open a Pull Request

### Reporting Issues

When reporting issues, please include:
- Python version (`python --version`)
- OS and version
- Full traceback
- Whether the issue occurs with `auto_cookie=True` or `cookie_path`

---

## 📄 License

This project is licensed under the **MIT License**. See [LICENSE](LICENSE) for full details.

---

## ⚠️ Disclaimer

This is an **unofficial, reverse-engineered** client and is **not affiliated with, endorsed by, or supported by Google**. Usage is subject to Google's Terms of Service. Use responsibly and at your own risk.

---

<div align="center">

**Built with ❤️ — Zero API Keys. Zero Limits.**

</div>
