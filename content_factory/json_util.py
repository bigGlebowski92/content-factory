"""Helpers for parsing JSON from model responses."""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)


def parse_model_json(content: str) -> Any:
    """Parse JSON from model output, tolerating markdown fences / leading prose."""
    text = (content or "").strip()
    if not text:
        raise json.JSONDecodeError("Empty model content", text, 0)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    fence = _FENCE_RE.search(text)
    if fence:
        return json.loads(fence.group(1).strip())

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start : end + 1])

    raise json.JSONDecodeError("No JSON object found", text, 0)
