# -*- coding: utf-8 -*-
"""
gemini_client/response.py
==========================
Official Google Gemini API-compatible response models.

Maps the scraped/WebSocket response data to the same shape returned
by the official ``google-genai`` Python SDK, so client code can be
migrated to the official SDK with zero changes.

Official SDK reference types this matches:
  - ``GenerateContentResponse``
  - ``Candidate``
  - ``Content``
  - ``Part``
  - ``UsageMetadata``
  - ``PromptFeedback``
  - ``SafetyRating``
  - ``FinishReason``

Usage::

    from gemini_client import Chatbot
    response = chatbot.ask("Hello")

    # Official-SDK style access
    print(response.text)                          # str
    print(response.candidates[0].content.parts[0].text)
    print(response.usage_metadata.total_token_count)
    print(response.candidates[0].finish_reason)   # "STOP"
    print(response.model)                         # "gemini-2.5-flash"
    print(response.error)                         # False

    # Legacy dict-style access (backward compatible)
    print(response["content"])
    print(response["images"])
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional


# ──────────────────────────────────────────────────────────────────────────────
# Primitive containers
# ──────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class InlineData:
    """Represents binary data (image, audio) embedded in a Part."""
    data: bytes
    mime_type: str

    def __repr__(self) -> str:
        return f"InlineData(mime_type={self.mime_type!r}, bytes={len(self.data)})"


@dataclass(frozen=True, slots=True)
class Part:
    """
    A single piece of content — text, image, or audio.

    Attributes
    ----------
    text : str, optional
        Text content (mutually exclusive with inline_data).
    inline_data : InlineData, optional
        Binary content such as images or audio.
    """
    text: Optional[str] = None
    inline_data: Optional[InlineData] = None

    def __repr__(self) -> str:
        if self.text is not None:
            preview = self.text[:60] + "..." if len(self.text) > 60 else self.text
            return f"Part(text={preview!r})"
        if self.inline_data:
            return f"Part(inline_data={self.inline_data!r})"
        return "Part()"


@dataclass(frozen=True, slots=True)
class Content:
    """
    A conversation turn — a role plus one or more Parts.

    Attributes
    ----------
    role : str
        ``"model"`` or ``"user"``.
    parts : list[Part]
        Ordered list of content parts.
    """
    role: str
    parts: List[Part] = field(default_factory=list)

    @property
    def text(self) -> str:
        """Concatenated text from all text parts."""
        return "".join(p.text for p in self.parts if p.text is not None)

    def __repr__(self) -> str:
        return f"Content(role={self.role!r}, parts={len(self.parts)})"


@dataclass(frozen=True, slots=True)
class SafetyRating:
    """Safety classification for a specific harm category."""
    category: str
    probability: str
    blocked: bool = False


@dataclass(frozen=True, slots=True)
class CitationSource:
    """A single citation / grounding source."""
    uri: str
    title: str = ""
    start_index: Optional[int] = None
    end_index: Optional[int] = None


@dataclass(frozen=True, slots=True)
class CitationMetadata:
    """Grounding citations returned with a response."""
    citation_sources: List[CitationSource] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class Candidate:
    """
    A single generated response candidate.

    Attributes
    ----------
    content : Content
        The model's response turn.
    finish_reason : str
        Why generation stopped. Common values: ``"STOP"``, ``"MAX_TOKENS"``,
        ``"SAFETY"``, ``"RECITATION"``, ``"OTHER"``.
    index : int
        Position of this candidate in the candidates list.
    safety_ratings : list[SafetyRating]
        Per-category safety scores.
    citation_metadata : CitationMetadata, optional
        Grounding sources if Google Search was used.
    token_count : int
        Approximate token count for this candidate.
    """
    content: Content
    finish_reason: str = "STOP"
    index: int = 0
    safety_ratings: List[SafetyRating] = field(default_factory=list)
    citation_metadata: Optional[CitationMetadata] = None
    token_count: int = 0

    @property
    def text(self) -> str:
        """Shortcut to the candidate's full text."""
        return self.content.text

    def __repr__(self) -> str:
        preview = self.text[:60] + "..." if len(self.text) > 60 else self.text
        return f"Candidate(index={self.index}, finish_reason={self.finish_reason!r}, text={preview!r})"


@dataclass(frozen=True, slots=True)
class UsageMetadata:
    """
    Token usage for the request/response.

    Attributes
    ----------
    prompt_token_count : int
        Tokens used by the prompt (approximate for scraped responses).
    candidates_token_count : int
        Tokens used by all candidates combined.
    total_token_count : int
        Sum of prompt + candidates tokens.
    """
    prompt_token_count: int = 0
    candidates_token_count: int = 0
    total_token_count: int = 0

    def __repr__(self) -> str:
        return (
            f"UsageMetadata(prompt={self.prompt_token_count}, "
            f"candidates={self.candidates_token_count}, "
            f"total={self.total_token_count})"
        )


@dataclass(frozen=True, slots=True)
class PromptFeedback:
    """Feedback about the prompt from the safety system."""
    block_reason: Optional[str] = None
    safety_ratings: List[SafetyRating] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────────────
# Top-level response
# ──────────────────────────────────────────────────────────────────────────────

class GenerateContentResponse:
    """
    Response from Gemini — mirrors the official ``google-genai`` SDK format.

    Supports both attribute access (official SDK style) and dict-style access
    (backward compat with the old ``ask()`` return value).

    Attributes
    ----------
    candidates : list[Candidate]
    usage_metadata : UsageMetadata
    prompt_feedback : PromptFeedback
    model : str
        The model that generated this response.
    conversation_id : str
    response_id : str
    images : list[dict]
        Extracted image URLs: ``[{"url": ..., "title": ..., "alt": ...}]``.
    error : bool
        True if this response represents an error condition.
    error_message : str, optional
        Human-readable error description when error=True.
    choices : list[dict]
        Raw choice list (internal, for backward compat).
    """

    __slots__ = (
        "candidates",
        "usage_metadata",
        "prompt_feedback",
        "model",
        "conversation_id",
        "response_id",
        "images",
        "error",
        "error_message",
        "choices",
        "_text_query",
        "_factuality",
    )

    def __init__(
        self,
        candidates: List[Candidate],
        usage_metadata: Optional[UsageMetadata] = None,
        prompt_feedback: Optional[PromptFeedback] = None,
        model: str = "",
        conversation_id: str = "",
        response_id: str = "",
        images: Optional[List[Dict[str, Any]]] = None,
        error: bool = False,
        error_message: Optional[str] = None,
        choices: Optional[List[Dict]] = None,
        text_query: str = "",
        factuality: Any = None,
    ):
        self.candidates = candidates
        self.usage_metadata = usage_metadata or UsageMetadata()
        self.prompt_feedback = prompt_feedback or PromptFeedback()
        self.model = model
        self.conversation_id = conversation_id
        self.response_id = response_id
        self.images = images or []
        self.error = error
        self.error_message = error_message
        self.choices = choices or []
        self._text_query = text_query
        self._factuality = factuality

    # ── Official SDK property ──────────────────────────────────────────────

    @property
    def text(self) -> str:
        """
        The text of the first candidate's first part.
        Returns empty string "" if there are no candidates or the response is an error.
        Matches ``response.text`` from the official SDK.
        """
        if self.error or not self.candidates:
            return ""
        return self.candidates[0].text or ""

    @property
    def parts(self) -> List[Part]:
        """Parts of the first candidate's content."""
        if not self.candidates:
            return []
        return self.candidates[0].content.parts

    # ── Dict-style backward compatibility ─────────────────────────────────

    def __getitem__(self, key: str) -> Any:
        """Support ``response["content"]``, ``response["images"]`` etc."""
        _MAP = {
            "content": self.text,
            "text": self.text,
            "images": self.images,
            "error": self.error,
            "conversation_id": self.conversation_id,
            "response_id": self.response_id,
            "choices": self.choices,
            "factualityQueries": self._factuality,
            "textQuery": self._text_query,
        }
        if key in _MAP:
            return _MAP[key]
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        """Support ``response.get("error")`` etc."""
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key: str) -> bool:
        try:
            self[key]
            return True
        except KeyError:
            return False

    def __iter__(self) -> Iterator[str]:
        return iter(["content", "text", "images", "error",
                     "conversation_id", "response_id", "choices",
                     "factualityQueries", "textQuery"])

    # ── Utilities ─────────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict (for JSON output, logging, etc.)."""
        return {
            "text": self.text,
            "model": self.model,
            "conversation_id": self.conversation_id,
            "response_id": self.response_id,
            "error": self.error,
            "error_message": self.error_message,
            "images": self.images,
            "candidates": [
                {
                    "index": c.index,
                    "finish_reason": c.finish_reason,
                    "text": c.text,
                    "token_count": c.token_count,
                }
                for c in self.candidates
            ],
            "usage_metadata": {
                "prompt_token_count": self.usage_metadata.prompt_token_count,
                "candidates_token_count": self.usage_metadata.candidates_token_count,
                "total_token_count": self.usage_metadata.total_token_count,
            },
        }

    def __bool__(self) -> bool:
        return not self.error

    def __repr__(self) -> str:
        if self.error:
            return f"GenerateContentResponse(error=True, message={self.error_message!r})"
        preview = (self.text or "")[:80]
        if len(self.text or "") > 80:
            preview += "..."
        return (
            f"GenerateContentResponse("
            f"text={preview!r}, "
            f"candidates={len(self.candidates)}, "
            f"images={len(self.images)}, "
            f"usage={self.usage_metadata!r})"
        )


# ──────────────────────────────────────────────────────────────────────────────
# Factory helpers
# ──────────────────────────────────────────────────────────────────────────────

def _estimate_tokens(text: str) -> int:
    """
    Rough token count estimate (≈ 4 chars per token for English).
    The scraped API does not return token counts, so we estimate.
    """
    return max(1, len(text) // 4)


def build_response(
    raw: Dict[str, Any],
    model_name: str = "",
) -> "GenerateContentResponse":
    """
    Convert the internal ``_ask_once()`` raw dict to a ``GenerateContentResponse``.

    Parameters
    ----------
    raw : dict
        The dict returned by ``AsyncChatbot._ask_once()``.
    model_name : str
        The model name string to embed in the response.

    Returns
    -------
    GenerateContentResponse
    """
    # Error response
    if raw.get("error"):
        return GenerateContentResponse(
            candidates=[],
            error=True,
            error_message=raw.get("content", "Unknown error"),
            model=model_name,
        )

    content_text = raw.get("content") or ""

    # Build candidates
    candidates = []
    raw_choices = raw.get("choices", [])
    if raw_choices:
        for idx, choice in enumerate(raw_choices):
            if not isinstance(choice, dict):
                continue
            choice_text = choice.get("content", "")
            if isinstance(choice_text, list):
                choice_text = choice_text[0] if choice_text else ""
            part = Part(text=choice_text or content_text)
            content = Content(role="model", parts=[part])
            candidates.append(Candidate(
                content=content,
                finish_reason="STOP",
                index=idx,
                token_count=_estimate_tokens(choice_text or content_text),
            ))
    else:
        # Single candidate from content field
        part = Part(text=content_text)
        content = Content(role="model", parts=[part])
        candidates.append(Candidate(
            content=content,
            finish_reason="STOP",
            index=0,
            token_count=_estimate_tokens(content_text),
        ))

    # Usage metadata (estimated — scraped API doesn't expose real counts)
    candidates_tokens = sum(c.token_count for c in candidates)
    prompt_tokens = _estimate_tokens(raw.get("textQuery") or "")
    usage = UsageMetadata(
        prompt_token_count=prompt_tokens,
        candidates_token_count=candidates_tokens,
        total_token_count=prompt_tokens + candidates_tokens,
    )

    return GenerateContentResponse(
        candidates=candidates,
        usage_metadata=usage,
        model=model_name,
        conversation_id=raw.get("conversation_id", ""),
        response_id=raw.get("response_id", ""),
        images=raw.get("images", []),
        error=False,
        choices=raw_choices,
        text_query=raw.get("textQuery", ""),
        factuality=raw.get("factualityQueries"),
    )


def build_error_response(
    message: str,
    model_name: str = "",
) -> "GenerateContentResponse":
    """Create a ``GenerateContentResponse`` for an error condition."""
    return GenerateContentResponse(
        candidates=[],
        error=True,
        error_message=message,
        model=model_name,
    )


# Alias to match official SDK name
GeminiResponse = GenerateContentResponse
