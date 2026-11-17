"""Game-agnostic command envelope and validation helpers."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from .errors import InvalidCommandError
@dataclass(frozen=True, slots=True)
class Command:
    """A timestamped, uniquely identified instruction.
    `action` is opaque to the kernel. It must be an immutable value object that
    supports ==; the active Rules object validates and interprets it.
    Construction does not validate; validation happens on Engine.submit().
    """
    command_id: str
    tick: int
    action: Any
def require_text(value: object, what: str) -> None:
    """Non-empty str that can be encoded as strict UTF-8."""
    if type(value) is not str:
        raise InvalidCommandError(f"{what} must be a str, got {type(value).__name__}")
    if value == "":
        raise InvalidCommandError(f"{what} must not be empty")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise InvalidCommandError(f"{what} is not valid Unicode text") from None
def require_int(value: object, what: str, *, minimum: int | None = None) -> None:
    """Exact int (bool and int subclasses are rejected)."""
    if type(value) is not int:
        raise InvalidCommandError(f"{what} must be an int, got {type(value).__name__}")
    if minimum is not None and value < minimum:
        raise InvalidCommandError(f"{what} must be >= {minimum}, got {value}")
