"""Validation for protocol values that are used in AT command strings or paths."""

from __future__ import annotations

import re


_SESSION_RE = re.compile(r"^[0-9]{14}$")
_CHUNK_RE = re.compile(r"^[0-9]{4}\.opus$")


def session_id(value: str) -> str:
    """Return a valid firmware session id, or raise :class:`ValueError`."""
    if not isinstance(value, str) or not _SESSION_RE.fullmatch(value):
        raise ValueError("session_id must be exactly 14 decimal digits (YYYYMMDDHHMMSS)")
    return value


def chunk_name(value: str) -> str:
    """Return a valid logical Clip chunk name, or raise :class:`ValueError`."""
    if not isinstance(value, str) or not _CHUNK_RE.fullmatch(value):
        raise ValueError("chunk name must be NNNN.opus")
    if value[:4] == "0000":
        raise ValueError("chunk number must be at least 0001")
    return value


def page(value: int, *, name: str = "page", maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be at most {maximum}")
    return value
