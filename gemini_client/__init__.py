# -*- coding: utf-8 -*-
"""
Gemini-Chat-API
===============
100% Unofficial Python Client for Google Gemini Web UI.
Uses browser cookies (__Secure-1PSID / __Secure-1PSIDTS) — Zero API Key Required.

Features:
  - Text chat & Multi-turn conversations
  - Real-time streaming responses (ask_stream)
  - Automatic cookie extraction from Chrome/Edge/Firefox/Brave
  - Image input analysis & Google image upload
  - Generated web image extraction
  - Custom proxy support & browser fingerprint impersonation (curl_cffi HTTP/2)
"""

from .core import Chatbot, AsyncChatbot
from .enums import Model, Endpoint, Headers
from .images import Image, WebImage, GeneratedImage
from .utils import upload_file, load_cookies
from .cookie_manager import CookieExtractor
from .memory import ConversationMemory, MemoryMessage, MultiUserMemoryManager
from .scale_engine import (
    HighScaleSupportEngine,
    HighScaleMemoryPool,
    AsyncSessionPool,
)
from . import server
from .response import (
    GenerateContentResponse,
    Candidate,
    Content,
    Part,
    UsageMetadata,
    SafetyRating,
    PromptFeedback,
    InlineData,
    CitationSource,
    CitationMetadata,
)
from . import unofficial_live
from .unofficial_live import (
    UnofficialLiveChatbot,
    UnofficialLiveWebSocket,
    UnofficialLiveBridgeServer,
)

__all__ = [
    # Main Chatbot Interface (100% Unofficial Cookie-based)
    "Chatbot",
    "AsyncChatbot",
    "CookieExtractor",
    "load_cookies",
    "upload_file",
    "Model",
    "Endpoint",
    "Headers",
    "Image",
    "WebImage",
    "GeneratedImage",
    # Conversation Context Memory & Multi-User Support Center Manager
    "ConversationMemory",
    "MemoryMessage",
    "MultiUserMemoryManager",
    # 500+ Concurrent High-Scale Architecture Engine
    "HighScaleSupportEngine",
    "HighScaleMemoryPool",
    "AsyncSessionPool",
    # AI Studio Web Dashboard & Server
    "server",
    # Advanced Unofficial Real-Time Live & WebSocket Engines
    "UnofficialLiveChatbot",
    "UnofficialLiveWebSocket",
    "UnofficialLiveBridgeServer",
    "unofficial_live",
    # Response Models
    "GenerateContentResponse",
    "Candidate",
    "Content",
    "Part",
    "UsageMetadata",
    "SafetyRating",
    "PromptFeedback",
    "InlineData",
    "CitationSource",
    "CitationMetadata",
]
