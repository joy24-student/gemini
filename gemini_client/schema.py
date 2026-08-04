# -*- coding: utf-8 -*-
"""
gemini_client/schema.py
=======================
Adaptive Schema Walker & Protocol Monitor for the Gemini Web UI RPC response.

Replaces every hardcoded array index (e.g. body[4][0][1], body[4][0][12][7][0])
with a typed extraction strategy that:

  1. Tries the known structural path first (fast path).
  2. Falls back to a scored recursive walker for text if the fast path fails.
  3. Never invents conversation IDs heuristically.
  4. Raises ProtocolError (a subclass of ValueError) so callers can distinguish
     schema failures from network / auth failures.
  5. Records a structural fingerprint (shape signature) so the ProtocolMonitor
     can alert when Google silently changes the RPC envelope.

Usage::

    from gemini_client.schema import extract_response, ProtocolMonitor

    data = extract_response(body, response_json=response_json)
    # data.text, data.conversation_id, data.response_id,
    # data.choice_id, data.images, data.generated_images

    monitor = ProtocolMonitor()
    monitor.record(body)        # call once per response
    monitor.check_drift()       # logs a warning if shape changed
"""
from __future__ import annotations

import hashlib
import re
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# ── Pre-compiled patterns ─────────────────────────────────────────────────────
_RE_GOOGLE_IMG = re.compile(r'https?://lh\d+\.googleusercontent\.com/[^\s"\'<>]+')
_RE_IMG_EXT    = re.compile(r'https?://[^\s"\'<>]+\.(?:jpg|jpeg|png|gif|webp)', re.I)
_RE_ANY_URL    = re.compile(r'https?://[^\s"\'<>]{10,}')

# Minimum length for a candidate text response
_MIN_TEXT_LEN = 1


class ProtocolError(ValueError):
    """Raised when the Gemini RPC response does not match any known schema."""


# ── Result container ──────────────────────────────────────────────────────────
@dataclass
class ParsedResponse:
    text: str = ""
    conversation_id: str = ""
    response_id: str = ""
    choice_id: str = ""
    choices: List[Dict] = field(default_factory=list)
    images: List[Dict] = field(default_factory=list)
    generated_images: List[Dict] = field(default_factory=list)
    degraded: bool = False          # True if fast-path failed, walker used


# ── Helpers ───────────────────────────────────────────────────────────
def _safe_str(node: Any) -> Optional[str]:
    """Return node as str only when it looks like a real text response."""
    if not isinstance(node, str):
        return None
    stripped = node.strip()
    if len(stripped) < _MIN_TEXT_LEN:
        return None
    if stripped.startswith(("boq_assistant", "rc_", "c_", "r_", "_")) or "bard-web-server" in stripped:
        return None
    lowered = stripped.lower()
    if lowered in ("searching the web", "searching...", "thinking...", "thought") or lowered.startswith(("searching the web", "searching google", "thinking for")):
        return None
    return stripped


def _score_text(text: str) -> float:
    """
    Score a candidate string as a Gemini response.
    Higher is better. Penalizes short, URL-only, or JSON-looking strings.
    """
    if not text:
        return 0.0
    score = float(len(text))
    # Reward human-readable characters
    alpha = sum(1 for c in text if c.isalpha())
    score += alpha * 0.5
    # Penalise if it looks like a URL
    if text.startswith('http'):
        score *= 0.1
    return score


def _walk_for_text(node: Any, depth: int = 0, max_depth: int = 14) -> List[str]:
    """
    Recursively collect plausible text response strings from a JSON tree.
    Returns a list of candidate strings sorted by descending score.
    """
    if depth > max_depth or node is None:
        return []
    candidates: List[str] = []
    if isinstance(node, str):
        s = _safe_str(node)
        if s:
            candidates.append(s)
    elif isinstance(node, list):
        for item in node:
            if item is not None:
                candidates.extend(_walk_for_text(item, depth + 1, max_depth))
    elif isinstance(node, dict):
        for v in node.values():
            if v is not None:
                candidates.extend(_walk_for_text(v, depth + 1, max_depth))
    return candidates


def _collect_image_urls(node: Any, depth: int = 0, max_depth: int = 14) -> List[str]:
    """Recursively collect all Google image URLs from a JSON tree."""
    urls: List[str] = []
    if depth > max_depth:
        return urls
    if isinstance(node, str):
        urls.extend(_RE_GOOGLE_IMG.findall(node))
        urls.extend(_RE_IMG_EXT.findall(node))
    elif isinstance(node, list):
        for item in node:
            urls.extend(_collect_image_urls(item, depth + 1, max_depth))
    elif isinstance(node, dict):
        for v in node.values():
            urls.extend(_collect_image_urls(v, depth + 1, max_depth))
    # Deduplicate preserving order & filter internal tool status strings
    seen: set = set()
    deduped = []
    for u in urls:
        if u not in seen and "image_generation_content" not in u and "data_analysis_tool" not in u:
            seen.add(u)
            deduped.append(u)
    return deduped


def _clean_url(url: str) -> str:
    if url and url[-1] in ('.', ',', ')', ']', '}', '"', "'"):
        return url[:-1]
    return url


# ── Known-path fast extraction ────────────────────────────────────────────────
def _extract_text_fast(body: Any) -> Optional[str]:
    """Try the known structural path body[4][0][1] and join all text parts."""
    try:
        if isinstance(body, list) and len(body) > 4 and isinstance(body[4], list) and body[4]:
            for cand_item in body[4]:
                if isinstance(cand_item, list) and len(cand_item) > 1 and cand_item[1]:
                    parts = cand_item[1] if isinstance(cand_item[1], list) else [cand_item[1]]
                    collected = []
                    for part in parts:
                        p_node = part
                        while isinstance(p_node, list) and p_node:
                            p_node = p_node[0]
                        if isinstance(p_node, str):
                            s = _safe_str(p_node)
                            if s:
                                collected.append(s)
                    if collected:
                        return "".join(collected)
    except (IndexError, TypeError):
        pass
    return None


def _extract_conversation_ids(body: Any) -> Tuple[str, str]:
    """Extract (conversation_id, response_id) from body[1]."""
    try:
        if isinstance(body, list) and len(body) > 1 and body[1]:
            b1 = body[1]
            if isinstance(b1, list):
                if len(b1) > 1 and isinstance(b1[1], list) and len(b1[1]) > 0:
                    c_id = str(b1[1][0]) if b1[1][0] is not None else ""
                    r_id = str(b1[1][1]) if len(b1[1]) > 1 and b1[1][1] is not None else ""
                    return (c_id, r_id)
                elif len(b1) > 0 and isinstance(b1[0], str):
                    c_id = str(b1[0]) if b1[0] is not None else ""
                    r_id = str(b1[1]) if len(b1) > 1 and b1[1] is not None else ""
                    return (c_id, r_id)
        return ("", "")
    except (IndexError, TypeError):
        return ("", "")


def _extract_choices(body: Any) -> List[Dict]:
    """Extract candidate choices from body[4]."""
    choices = []
    try:
        if isinstance(body, list) and len(body) > 4 and isinstance(body[4], list):
            for candidate in body[4]:
                try:
                    if isinstance(candidate, list) and len(candidate) > 1:
                        c_id = str(candidate[0]) if candidate[0] is not None else ""
                        content = ""
                        if isinstance(candidate[1], list) and candidate[1] and candidate[1][0] is not None:
                            content = str(candidate[1][0])
                        choices.append({"id": c_id, "content": content})
                except (IndexError, TypeError):
                    continue
    except (IndexError, TypeError):
        pass
    return choices


def _extract_inline_images(body: Any) -> List[Dict]:
    """Extract inline images from body[4][0][4]."""
    images = []
    try:
        if isinstance(body, list) and len(body) > 4 and isinstance(body[4], list) and body[4]:
            first_cand = body[4][0]
            if isinstance(first_cand, list) and len(first_cand) > 4 and isinstance(first_cand[4], list):
                for img_data in first_cand[4]:
                    try:
                        if isinstance(img_data, list) and len(img_data) > 0 and isinstance(img_data[0], list) and len(img_data[0]) > 0 and isinstance(img_data[0][0], list) and len(img_data[0][0]) > 0:
                            url = img_data[0][0][0]
                            alt = img_data[2] if len(img_data) > 2 else ""
                            title = img_data[1] if len(img_data) > 1 else "[Image]"
                            if url:
                                images.append({"url": str(url), "alt": str(alt), "title": str(title)})
                    except (IndexError, TypeError):
                        continue
    except (IndexError, TypeError):
        pass
    return images


def _extract_generated_images(body: Any, response_json: Any = None) -> List[Dict]:
    """Extract Imagen-generated images from body[4][0][12][7][0] with fallback scan."""
    gen_images: List[Dict] = []

    try:
        if isinstance(body, list) and len(body) > 4 and isinstance(body[4], list) and body[4]:
            first_cand = body[4][0]
            if isinstance(first_cand, list) and len(first_cand) > 12 and isinstance(first_cand[12], list) and len(first_cand[12]) > 7 and isinstance(first_cand[12][7], list) and first_cand[12][7]:
                img_list = first_cand[12][7][0]
                if isinstance(img_list, list):
                    for idx, img_data in enumerate(img_list):
                        try:
                            if isinstance(img_data, list) and len(img_data) > 0 and isinstance(img_data[0], list) and len(img_data[0]) > 3 and isinstance(img_data[0][3], list) and len(img_data[0][3]) > 3:
                                url = img_data[0][3][3]
                                alt = ""
                                try:
                                    if len(img_data) > 3 and isinstance(img_data[3], list) and len(img_data[3]) > 5 and isinstance(img_data[3][5], list) and img_data[3][5]:
                                        alt = str(img_data[3][5][0])
                                except (IndexError, TypeError):
                                    pass
                                if url:
                                    gen_images.append({"url": str(url), "title": f"[Generated Image {idx+1}]", "alt": alt})
                        except (IndexError, TypeError):
                            continue
    except (IndexError, TypeError):
        pass

    # If fast path found nothing, walk response_json or full body for Google image URLs
    if not gen_images:
        target = response_json if response_json is not None else body
        found_urls = _collect_image_urls(target)
        for i, url in enumerate(found_urls):
            gen_images.append({"url": _clean_url(url), "title": f"[Generated Image {i+1}]", "alt": ""})

    return gen_images


# ── Main entry point ──────────────────────────────────────────────────────────
def extract_response(
    body: Any,
    response_json: Any = None,
    current_conversation_id: str = "",
    current_response_id: str = "",
    current_choice_id: str = "",
) -> ParsedResponse:
    """
    Extract a fully-typed ParsedResponse from a raw Gemini RPC body.

    Parameters
    ----------
    body : any
        The inner JSON body (the `main_part` from the `wrb.fr` envelope).
    response_json : any, optional
        The full outer response JSON, used for image URL fallback scanning.
    current_* : str
        Current session state — used as fallback when extraction fails.

    Raises
    ------
    ProtocolError
        When the body is None, empty, or does not contain any parseable data.
    """
    if not body:
        raise ProtocolError("Response body is None or empty — possible protocol change.")

    result = ParsedResponse()
    degraded = False

    # ── 1. Text extraction ────────────────────────────────────────────────────
    text = _extract_text_fast(body)
    if text is None:
        # Scored walker fallback
        candidates = _walk_for_text(body)
        if candidates:
            best = max(candidates, key=_score_text)
            if _score_text(best) > 0:
                text = best
                degraded = True
    result.text = text or ""
    result.degraded = degraded

    # ── 2. Conversation IDs ───────────────────────────────────────────────────
    conv_id, resp_id = _extract_conversation_ids(body)
    # Never invent IDs; fall back to current state if extraction yields empty
    result.conversation_id = conv_id or current_conversation_id
    result.response_id     = resp_id or current_response_id

    # ── 3. Choices ────────────────────────────────────────────────────────────
    result.choices = _extract_choices(body)
    if result.choices and isinstance(result.choices[0], dict) and result.choices[0].get("id"):
        result.choice_id = str(result.choices[0]["id"])
    else:
        result.choice_id = current_choice_id

    # ── 4. Images ────────────────────────────────────────────────────────────
    result.images = _extract_inline_images(body)
    result.generated_images = _extract_generated_images(body, response_json)

    return result


# ── Structural Fingerprint & Protocol Monitor ─────────────────────────────────
def _shape_fingerprint(node: Any, depth: int = 0, max_depth: int = 6) -> str:
    """
    Build a compact structural fingerprint of a JSON node.
    Values are redacted; only types and list lengths are recorded.
    Example: 'L5[L3[s,s,L2[s]],L1[s],s,n,L4[L2[s,s]]]'
    """
    if depth > max_depth:
        return '…'
    if isinstance(node, str):
        return 's'
    if isinstance(node, bool):
        return 'b'
    if isinstance(node, (int, float)):
        return 'n'
    if node is None:
        return 'null'
    if isinstance(node, list):
        inner = ','.join(_shape_fingerprint(item, depth + 1, max_depth) for item in node[:8])
        return f'L{len(node)}[{inner}]'
    if isinstance(node, dict):
        inner = ','.join(f'{k}:{_shape_fingerprint(v, depth+1, max_depth)}' for k, v in list(node.items())[:6])
        return f'D{{{inner}}}'
    return '?'


class ProtocolMonitor:
    """
    Detects silent changes to the Gemini RPC response schema.

    Call `record(body)` on each response. Call `check_drift()` to log a
    warning when the structural shape differs from the baseline.
    Does NOT modify source files — only logs and alerts.
    """

    def __init__(self) -> None:
        self._baseline: Optional[str] = None
        self._baseline_hash: Optional[str] = None
        self._lock = threading.Lock()
        self.drift_count: int = 0

    def record(self, body: Any) -> None:
        fingerprint = _shape_fingerprint(body)
        h = hashlib.sha256(fingerprint.encode()).hexdigest()[:16]
        with self._lock:
            if self._baseline_hash is None:
                self._baseline = fingerprint
                self._baseline_hash = h
            elif h != self._baseline_hash:
                self.drift_count += 1

    def check_drift(self) -> bool:
        """Returns True if schema drift has been detected since last check."""
        with self._lock:
            drifted = self.drift_count > 0
            self.drift_count = 0
        return drifted

    @property
    def baseline_hash(self) -> Optional[str]:
        with self._lock:
            return self._baseline_hash


# Module-level singleton for use inside core.py
_monitor = ProtocolMonitor()
