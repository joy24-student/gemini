# Full System Architecture & Comprehensive Documentation — Gemini Unofficial API

## 1. Executive Summary & Project Overview

The **Gemini Unofficial API** package (`gemini_client`) is a high-performance Python and JavaScript library designed to interact with Google Gemini's Web UI (`gemini.google.com`) **100% unofficially**, requiring **zero official Google AI Studio API keys**.

It reverse-engineers the web interface RPC protocol (`StreamGenerate` and `batchexecute`), using browser session cookies (`__Secure-1PSID` and `__Secure-1PSIDTS`).

### Key Highlights
- **100% Free / Unofficial**: Operates via web session cookies; no paid API keys required.
- **Automatic Browser Cookie Extraction**: Automatically retrieves authentication cookies from locally installed browsers (Chrome, Edge, Firefox, Brave).
- **HTTP/2 & Speed Optimization**: Built on `httpx` with connection pooling, `orjson` parsing (3x–5x speedup), pre-compiled regex, and thread-safe lock-protected token refresh.
- **Official SDK-Compatible Response Surface**: Returns `GenerateContentResponse` objects with `.text`, `.candidates`, `.usage_metadata`, and `.parts`, while maintaining backwards-compatible dictionary access (`response["content"]`).
- **User-Friendly Context Memory Manager**:
  - **Named Memory Sessions**: Auto-saves and auto-resumes named chat sessions (`session_name="my_assistant"`).
  - **System Instructions**: Define custom system prompt instructions that persist across conversations.
  - **Auto History Tracking & Trimming**: Automatically records user prompts & model responses into `ConversationMemory`, managing token windows (`max_messages`).
  - **History Inspection & Context Prompt Formatting**: Inspect prior turns with `memory.get_history()` or format full prompt context via `memory.get_context_prompt()`.
- **Advanced Real-Time Live Engines**:
  - **Official-Protocol WebSocket Engine (`UnofficialLiveWebSocket`)**: Translates Gemini Web UI deltas into official `BidiGenerateContentServerContent` JSON frames (`modelTurn`, `parts`, `text`, `audio/pcm;rate=24000` base64 `inlineData`) instantly in <5ms.
  - **Local WebSocket Bridge Server (`UnofficialLiveBridgeServer`)**: Runs a local WebSocket server (`ws://127.0.0.1:9000`) matching the official Gemini Live protocol. Any application designed for official Gemini Live can connect with **0 API keys**!
  - **Sentence-Pipelined Voice Engine (`PipelineLiveSession`)**: Buffers text into sentence fragments and synthesizes audio concurrently (<200ms latency).
  - **Playwright 100% Background Engine (`PlaywrightLiveSession`)**: Automates headless Chromium operating silently in the background.

---

## 2. System Architecture Diagram

```
                                  ┌────────────────────────────────────────────────────────┐
                                  │               GEMINI UNOFFICIAL SYSTEM                 │
                                  └────────────────────────────────────────────────────────┘
                                                               │
                                         ┌─────────────────────┴─────────────────────┐
                                         ▼                                           ▼
                      ┌────────────────────────────────────┐             ┌───────────────────────────────────┐
                      │    Python Engine (gemini_client)   │             │   Node.js Client (gemini.js)      │
                      └────────────────────────────────────┘             └───────────────────────────────────┘
                                         │
        ┌────────────────────────────────┼────────────────────────────────┬────────────────────────────────┐
        ▼                                ▼                                ▼                                ▼
┌───────────────┐               ┌──────────────────┐             ┌─────────────────┐             ┌──────────────────┐
│  Core Client  │               │ Cookie Extractor │             │ Response Engine │             │  Live Real-Time  │
│  (core.py)    │               │(cookie_manager)  │             │  (response.py)  │             │ (unofficial_live)│
└───────────────┘               └──────────────────┘             └─────────────────┘             └──────────────────┘
  • Chatbot                       • Chrome / Edge                  • GenerateContentResponse       • Pipeline Session
  • AsyncChatbot                  • Firefox / Brave                • Candidates & Parts            • Playwright Session
  • ask()                         • OS Decryption                  • Token Estimates               • Speaker Stream Queue
  • ask_stream()                  • Keyring / DPAPI                • Backward Compat Dict          • Sentence Chunking
```

---

## 3. Deep-Dive Module Breakdown

### 3.1 Authentication & Cookie Extraction (`cookie_manager.py` & `utils.py`)
Google Gemini Web UI relies on two essential security cookies:
1. `__Secure-1PSID`: Main session identifier.
2. `__Secure-1PSIDTS`: Rotating timestamp token for anti-replay protection.

#### `CookieExtractor`
- Utilizes `browser_cookie3` to scan local browser user-data directories.
- Automatically decrypts browser cookie databases on Windows (DPAPI), macOS (Keychain), and Linux (SecretService).
- Extracts `__Secure-1PSID` and `__Secure-1PSIDTS` automatically without requiring manual user input.

#### `SNlM0e` Token Extraction
Every request to Gemini's `StreamGenerate` endpoint requires an internal CSRF token named `SNlM0e`.
- `AsyncChatbot` sends an initial GET request to `https://gemini.google.com/app`.
- The HTML response is scanned using a pre-compiled regex `_RE_SNLM0E` (`"SNlM0e":"([^"]+)"`).
- On session expiration (`401`/`403`), `_refresh_snlm0e()` automatically triggers cookie rotation (`ROTATE_COOKIES` endpoint) under an `asyncio.Lock()` to prevent thundering-herd issues.

---

### 3.2 Core HTTP/2 Engine (`core.py`)

#### `AsyncChatbot`
The foundational async engine built on `httpx.AsyncClient` with HTTP/2 support.

- **`create(secure_1psid, secure_1psidts, proxy=None, timeout=20, model=Model.UNSPECIFIED)`**:
  Factory constructor that initializes the HTTP/2 session and fetches the `SNlM0e` token asynchronously.
- **`ask(message, image=None, retry=3, retry_delay=1.5)`**:
  Sends a query to Gemini's `StreamGenerate` RPC endpoint. Encapsulates retry logic with exponential backoff on transient network failures. Returns a `GenerateContentResponse`.
- **`ask_stream(message, image=None)`**:
  Async generator yielding incremental text deltas as newline-delimited JSON parts arrive from Google's chunked response.
- **`save_conversation(file_path, conversation_name)` & `load_conversation(file_path, conversation_name)`**:
  Persists conversation IDs (`conversation_id`, `response_id`, `choice_id`) to JSON files, enabling seamless multi-turn sessions across restarts.

#### `Chatbot`
Synchronous wrapper around `AsyncChatbot`. Manages an internal `asyncio` event loop so standard sync scripts can invoke `bot.ask()` or `for chunk in bot.ask_stream()`.

---

### 3.3 Response Models (`response.py`)

Provides official Google AI SDK-compatible objects (`google-genai` shape) so applications can swap between official and unofficial clients seamlessly.

#### Class Hierarchy
- **`GenerateContentResponse`**: Top-level response object.
  - `.text` (str): Full response text.
  - `.candidates` (List[Candidate]): Generated response candidates.
  - `.usage_metadata` (UsageMetadata): Estimated prompt and output token counts.
  - `.images` (List[dict]): Extracted web and generated image URLs.
  - `.error` (bool): True if request failed.
  - **Dictionary Compatibility**: Supports `response["content"]`, `response["images"]`, `response["conversation_id"]` for backwards compatibility.
- **`Candidate`**: Contains `.content` (`Content` object), `.finish_reason` (`"STOP"`), `.index`, and `.token_count`.
- **`Content`**: Represents a turn with `role="model"` and a list of `Part` objects.
- **`Part`**: Holds `.text` or `.inline_data`.

---

### 3.4 Unofficial Real-Time Live Engines (`gemini_client/unofficial_live/`)

Designed for sub-200ms real-time voice and text conversations without official API keys.

#### 1. Sentence-Pipelined Voice Engine (`pipeline_session.py`)
- **`PipelineLiveSession`**:
  Connects to `AsyncChatbot.ask_stream()`.
  - As tokens stream in, a regex matcher (`_SENTENCE_PATTERN`) accumulates text until sentence boundaries (`.`, `!`, `?`, `\n`) are formed.
  - As soon as Sentence 1 completes, an async worker immediately dispatches TTS audio synthesis for Sentence 1 **while Gemini is still generating Sentence 2**.
- **`UnofficialSpeakerStream`**:
  Thread-safe, non-blocking `PyAudio` audio stream queue. Plays PCM audio seamlessly without blocking the main event loop.

#### 2. Playwright Headless Chromium Engine (`playwright_session.py`)
- **`PlaywrightLiveSession`**:
  Launches a persistent Playwright Chromium browser process.
  - Automatically injects `__Secure-1PSID` and `__Secure-1PSIDTS` cookies into browser context.
  - Navigates to `https://gemini.google.com/app`.
  - Listens directly to incoming network responses & DOM updates for sub-50ms token updates.
  - Grants virtual microphone & camera permissions (`--use-fake-ui-for-media-stream`).

---

### 3.5 Image Analysis & File Upload (`images.py` & `utils.py`)

#### Image Upload Flow (`upload_file`)
1. Reads image bytes or local image path (PNG, JPG, WebP).
2. Sends POST request to Google's push upload server (`https://content-push.googleapis.com/upload/`).
3. Obtains a Google Upload ID (e.g. `feeds/mcudyrk...`).
4. Structures the inner JSON payload in `StreamGenerate`:
   `[[message], [[[upload_id, 1]]], [conv_id, resp_id, choice_id]]`.

#### Image Extractors (`images.py`)
- **`WebImage`**: Extracted web images returned by Gemini. Supports async downloading.
- **`GeneratedImage`**: Images generated by Gemini's Imagen model embedded in response payloads. Downloads using cookie authentication.

---

### 3.6 Node.js / JavaScript Client (`gemini.js`)

A standalone CommonJS Node.js client using `axios`.
- Features updated 2024 build label (`bl=boq_assistant-bard-web-server_20240625.13_p0`).
- Parses `wrb.fr` outer JSON arrays.
- Supports multi-turn conversations and image extraction.

---

## 4. API Reference & Code Examples

### 4.1 Basic Chat (Auto-Cookie)
```python
from gemini_client import Chatbot, Model

# Auto-extracts cookies from default browser
bot = Chatbot(auto_cookie=True, model=Model.G_2_5_FLASH)

response = bot.ask("What are the 3 laws of robotics?")
print("Gemini:", response.text)
print("Tokens used:", response.usage_metadata.total_token_count)
```

### 4.2 Real-Time Streaming
```python
from gemini_client import Chatbot

bot = Chatbot(auto_cookie=True)

print("Gemini: ", end="", flush=True)
for chunk in bot.ask_stream("Explain machine learning in simple terms."):
    print(chunk, end="", flush=True)
print()
```

### 4.3 Image Analysis
```python
from gemini_client import Chatbot

bot = Chatbot(auto_cookie=True)
response = bot.ask("Describe what you see in this image", image="sample.jpg")

print(response.text)
```

### 4.4 Real-Time Live Voice Pipeline
```python
import asyncio
from gemini_client import UnofficialLiveChatbot

async def main():
    async with UnofficialLiveChatbot(auto_cookie=True) as bot:
        await bot.start_voice_pipeline()

asyncio.run(main())
```

---

## 5. Performance Benchmarks & Optimizations

| Optimization | Method Used | Benefit |
|---|---|---|
| **HTTP/2 Multiplexing** | `httpx.AsyncClient(http2=True)` | Eliminates per-request TCP handshakes |
| **Fast JSON Parsing** | `orjson` (with `json` fallback) | 3x–5x faster payload serialization |
| **Regex Pre-compilation** | Module-level `re.compile()` | Zero regex re-compilation overhead |
| **Lock Token Refresh** | `asyncio.Lock()` | Prevents thundering-herd on cookie rotation |
| **Sentence TTS Pipelining** | Sentence-boundary queueing | Sub-200ms voice response start |

---

## 6. Security & Best Practices

1. **Cookie Confidentiality**: `__Secure-1PSID` grants full access to your Google account session. Never commit cookie JSON files to public repositories.
2. **Session Lifespan**: `__Secure-1PSIDTS` rotates periodically. `CookieExtractor` automatically fetches fresh cookies from your browser database.
