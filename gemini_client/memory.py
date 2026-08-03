# -*- coding: utf-8 -*-
"""
gemini_client/memory.py
========================
User-Friendly Context Memory Manager for Gemini Unofficial API.

Provides automatic conversation history tracking, named session persistence,
context trimming, system prompt management, and multi-user support center sessions.

Features:
  1. Automatic History Tracking: Stores user & model turns with timestamps and metadata.
  2. Persistent Named Sessions: Save & resume named chat sessions (`memory.save("coding_bot")`).
  3. Automatic Context Window Management: Automatically trims oldest turns when exceeding `max_messages`.
  4. System Instruction Support: Set system instructions that persist across sessions.
  5. Multi-User Support Center (`MultiUserMemoryManager`): Isolated per-user memory sessions for concurrent support center applications.
  6. Non-Blocking Disk I/O: Auto-save uses asyncio.to_thread() inside async contexts to avoid blocking the event loop.
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class MemoryMessage:
    """Represents a single turn in the conversation memory."""
    role: str                      # "user" or "model"
    text: str                      # Content text
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    images: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryMessage":
        return cls(
            role=data.get("role", "user"),
            text=data.get("text", ""),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
            images=data.get("images", []),
            metadata=data.get("metadata", {}),
        )


class ConversationMemory:
    """
    Manages conversational memory, history persistence, and context trimming.

    Parameters
    ----------
    session_name : str, optional
        Unique session name. If provided, enables automatic auto-save/load.
    system_instruction : str, optional
        System prompt or context instructions for the AI.
    max_messages : int
        Maximum number of messages to retain in memory (default 50).
    storage_dir : str
        Directory to store saved session JSON files (default "~/.gemini/memory").
    """

    def __init__(
        self,
        session_name: Optional[str] = None,
        system_instruction: Optional[str] = None,
        max_messages: int = 50,
        storage_dir: Optional[str] = None,
    ):
        self.session_name = session_name
        self.system_instruction = system_instruction
        self.max_messages = max_messages
        self.messages: List[MemoryMessage] = []

        if storage_dir:
            self.storage_dir = Path(storage_dir)
            try:
                self.storage_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
        else:
            from gemini_client.utils import ensure_data_dir
            self.storage_dir = ensure_data_dir("memory")

        # Auto-load if session_name is specified and file exists
        if self.session_name:
            self.load(self.session_name)

    def add_user_message(
        self,
        text: str,
        images: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MemoryMessage:
        """Add a user message turn to memory."""
        msg = MemoryMessage(
            role="user",
            text=text,
            images=images or [],
            metadata=metadata or {},
        )
        self.messages.append(msg)
        self._trim_history()
        self._auto_save()
        return msg

    def add_model_message(
        self,
        text: str,
        images: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MemoryMessage:
        """Add a model response turn to memory."""
        msg = MemoryMessage(
            role="model",
            text=text,
            images=images or [],
            metadata=metadata or {},
        )
        self.messages.append(msg)
        self._trim_history()
        self._auto_save()
        return msg

    def get_history(self) -> List[MemoryMessage]:
        """Return the list of recorded conversation turns."""
        return list(self.messages)

    # Language label maps — covers major scripts without any external library
    _LANG_LABELS = {
        "bn": ("সিস্টেম নির্দেশ", "পূর্ববর্তী কথোপকথন", "ব্যবহারকারী", "জেমিনি"),
        "ar": ("تعليمات النظام", "المحادثة السابقة", "المستخدم", "جيميني"),
        "hi": ("सिस्टम निर्देश", "पिछली बातचीत", "उपयोगकर्ता", "जेमिनी"),
        "zh": ("系统指令", "之前的对话", "用户", "Gemini"),
        "ja": ("システム指示", "以前の会話", "ユーザー", "Gemini"),
        "ko": ("시스템 지침", "이전 대화", "사용자", "Gemini"),
        "ru": ("Системная инструкция", "Предыдущий разговор", "Пользователь", "Gemini"),
        "de": ("Systemanweisung", "Vorheriges Gespräch", "Nutzer", "Gemini"),
        "fr": ("Instruction système", "Conversation précédente", "Utilisateur", "Gemini"),
        "es": ("Instrucción del sistema", "Conversación anterior", "Usuario", "Gemini"),
        "pt": ("Instrução do sistema", "Conversa anterior", "Usuário", "Gemini"),
    }
    _DEFAULT_LABELS = ("System Instruction", "Previous Conversation Memory", "User", "Gemini")

    @staticmethod
    def _detect_lang(text: str) -> str:
        """
        Lightweight script detection using Unicode block ranges.
        Returns a 2-letter code for major non-Latin scripts, 'en' otherwise.
        No external packages required.
        """
        for ch in text[:80]:  # sample first 80 chars
            cp = ord(ch)
            if 0x0980 <= cp <= 0x09FF: return "bn"   # Bengali
            if 0x0600 <= cp <= 0x06FF: return "ar"   # Arabic
            if 0x0900 <= cp <= 0x097F: return "hi"   # Devanagari (Hindi)
            if 0x4E00 <= cp <= 0x9FFF: return "zh"   # CJK (Chinese)
            if 0x3040 <= cp <= 0x30FF: return "ja"   # Hiragana/Katakana (Japanese)
            if 0xAC00 <= cp <= 0xD7FF: return "ko"   # Korean
            if 0x0400 <= cp <= 0x04FF: return "ru"   # Cyrillic (Russian)
        return "en"

    def get_context_prompt(self, current_message: str) -> str:
        """
        Format conversation history + system instruction into a full contextual prompt.

        Automatically detects the language of the current message and emits
        context section labels in that language, so Gemini responds in the
        same language as the user without any external dependency.

        Ensures full memory continuity even if the underlying API session resets.
        """
        lang = self._detect_lang(current_message)
        labels = self._LANG_LABELS.get(lang, self._DEFAULT_LABELS)
        sys_label, history_label, user_label, _ = labels

        parts = []

        if self.system_instruction:
            parts.append(f"[{sys_label}]\n{self.system_instruction}\n")

        if self.messages:
            parts.append(f"[{history_label}]")
            for msg in self.messages[-self.max_messages:]:
                label = user_label if msg.role == "user" else "Gemini"
                parts.append(f"{label}: {msg.text}")
            parts.append("")

        parts.append(f"{user_label}: {current_message}")
        return "\n".join(parts)

    def clear(self) -> None:
        """Clear all messages from memory."""
        self.messages.clear()
        self._auto_save()

    def _trim_history(self) -> None:
        """Trim oldest messages if exceeding max_messages."""
        if len(self.messages) > self.max_messages:
            self.messages = self.messages[-self.max_messages:]

    def _auto_save(self) -> None:
        """
        Non-blocking auto-save.

        - Inside a running asyncio event loop: schedules a background thread task
          via asyncio.to_thread() so disk I/O never blocks the loop.
        - Outside an event loop (sync callers): runs in a daemon threading.Thread
          so it never blocks the caller.
        - Debounced: skips the save if last save was < 2 seconds ago to avoid
          disk thrashing under rapid-fire messages (e.g. streaming responses).
        """
        if not self.session_name:
            return

        # Debounce: skip if we saved very recently
        now = time.monotonic()
        last = getattr(self, "_last_save_time", 0.0)
        if now - last < 2.0:
            return
        self._last_save_time: float = now

        try:
            loop = asyncio.get_running_loop()
            # We are inside an async context — schedule non-blocking thread
            loop.create_task(asyncio.to_thread(self._save_sync, self.session_name))
        except RuntimeError:
            # No running loop — use a daemon thread so we never block the caller
            t = threading.Thread(
                target=self._save_sync, args=(self.session_name,), daemon=True
            )
            t.start()

    def _save_sync(self, name_or_path: str) -> None:
        """Synchronous disk write used by _auto_save (always called in a thread)."""
        try:
            self.save(name_or_path)
        except Exception:
            pass

    def save(self, name_or_path: str) -> str:
        """
        Save conversation memory to a JSON file.
        """
        target_path = self._resolve_path(name_or_path)
        data = {
            "session_name": self.session_name or name_or_path,
            "system_instruction": self.system_instruction,
            "updated_at": datetime.now().isoformat(),
            "messages": [msg.to_dict() for msg in self.messages],
        }
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return str(target_path)

    def load(self, name_or_path: str) -> bool:
        """
        Load conversation memory from a JSON file.
        """
        target_path = self._resolve_path(name_or_path)
        if not target_path.exists():
            return False
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.session_name = data.get("session_name", self.session_name)
            self.system_instruction = data.get("system_instruction", self.system_instruction)
            self.messages = [MemoryMessage.from_dict(m) for m in data.get("messages", [])]
            return True
        except Exception:
            return False

    def _resolve_path(self, name_or_path: str) -> Path:
        p = Path(name_or_path)
        if p.suffix == ".json" or "/" in name_or_path or "\\" in name_or_path:
            return p
        return self.storage_dir / f"{name_or_path}.json"

    def __len__(self) -> int:
        return len(self.messages)

    def __repr__(self) -> str:
        return f"ConversationMemory(session={self.session_name!r}, turns={len(self.messages)})"


class MultiUserMemoryManager:
    """
    Thread-Safe Multi-User Session Memory Pool for Support Center Applications.

    Manages isolated `ConversationMemory` instances per `user_id` / `ticket_id`.

    Parameters
    ----------
    default_system_instruction : str, optional
        Global support system instructions applied to all customer chats.
    storage_dir : str, optional
        Directory where per-user memory JSON files are saved.
    max_messages_per_user : int
        Maximum message history per user (default 30).

    Usage::

        memory_pool = MultiUserMemoryManager(
            default_system_instruction="You are Customer Support Agent for Acme Store."
        )

        # Customer 101 sends a query
        response = memory_pool.ask_user(chatbot, user_id="cust_101", message="Order #402 status?")

        # Customer 102 sends a query concurrently
        response2 = memory_pool.ask_user(chatbot, user_id="cust_102", message="How to reset password?")
    """

    def __init__(
        self,
        default_system_instruction: Optional[str] = None,
        storage_dir: Optional[str] = None,
        max_messages_per_user: int = 30,
    ):
        self.default_system_instruction = default_system_instruction
        self.max_messages_per_user = max_messages_per_user
        if storage_dir:
            self.storage_dir = Path(storage_dir)
            try:
                self.storage_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
        else:
            from gemini_client.utils import ensure_data_dir
            self.storage_dir = ensure_data_dir("support_memory")

        self._user_memories: Dict[str, ConversationMemory] = {}
        self._lock = threading.Lock()

    def get_user_memory(
        self,
        user_id: str,
        system_instruction: Optional[str] = None,
    ) -> ConversationMemory:
        """
        Get or create isolated ConversationMemory instance for a specific user_id.
        Automatically loads prior conversation if saved on disk.
        """
        with self._lock:
            if user_id not in self._user_memories:
                sys_inst = system_instruction or self.default_system_instruction
                user_mem = ConversationMemory(
                    session_name=f"user_{user_id}",
                    system_instruction=sys_inst,
                    max_messages=self.max_messages_per_user,
                    storage_dir=str(self.storage_dir),
                )
                self._user_memories[user_id] = user_mem
            return self._user_memories[user_id]

    def ask_user(
        self,
        chatbot: Any,
        user_id: str,
        message: str,
        image: Optional[Any] = None,
    ) -> Any:
        """
        Synchronously process a support message for a specific customer user_id,
        injecting their isolated conversation history context.
        """
        user_mem = self.get_user_memory(user_id)
        context_prompt = user_mem.get_context_prompt(message)

        # Record user message in isolated user memory
        user_mem.add_user_message(message)

        # Query chatbot with contextual prompt
        response = chatbot.ask(context_prompt, image=image)

        # Record model response in user memory
        if getattr(response, "text", None):
            user_mem.add_model_message(response.text)
        elif isinstance(response, dict) and response.get("content"):
            user_mem.add_model_message(response["content"])

        return response

    async def async_ask_user(
        self,
        async_chatbot: Any,
        user_id: str,
        message: str,
        image: Optional[Any] = None,
    ) -> Any:
        """
        Asynchronously process a support message for a specific customer user_id.
        """
        user_mem = self.get_user_memory(user_id)
        context_prompt = user_mem.get_context_prompt(message)

        user_mem.add_user_message(message)

        response = await async_chatbot.ask(context_prompt, image=image)

        if getattr(response, "text", None):
            user_mem.add_model_message(response.text)
        elif isinstance(response, dict) and response.get("content"):
            user_mem.add_model_message(response["content"])

        return response

    def clear_user_memory(self, user_id: str) -> None:
        """Clear memory for a closed support ticket or user session."""
        with self._lock:
            if user_id in self._user_memories:
                self._user_memories[user_id].clear()
                del self._user_memories[user_id]

    def list_active_users(self) -> List[str]:
        """Return list of active user IDs currently in memory."""
        with self._lock:
            return list(self._user_memories.keys())
