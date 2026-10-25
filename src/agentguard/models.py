"""Internal records. Raw payloads are intentionally excluded from repr and reports."""

from dataclasses import dataclass, field
from typing import Any


class InputError(ValueError):
    """Invalid or unsupported input, with diagnostics safe to show in a CLI."""


@dataclass(frozen=True)
class Limits:
    max_input_bytes: int = 64 * 1024 * 1024
    max_total_bytes: int = 128 * 1024 * 1024
    max_line_bytes: int = 2 * 1024 * 1024
    max_archive_entries: int = 2048
    max_sessions: int = 256
    max_events: int = 200_000
    max_compression_ratio: int = 200

    def __post_init__(self) -> None:
        if any(type(value) is not int or value < 1 for value in vars(self).values()):
            raise ValueError("Limits must be positive integers")


@dataclass(frozen=True)
class LoadedSession:
    session_id: str
    source: str
    version: int
    is_seeded: bool
    parent_session: str | None
    rows: tuple[dict[str, Any], ...] = field(repr=False)


@dataclass(frozen=True)
class Event:
    seq: int
    timestamp_ms: int | None
    kind: str
    turn: int | None
    step: int | None
    inherited: bool = False
    source_kind: str | None = None
    guard_name: str | None = None
    tool_name: str | None = None
    call_id: str | None = None
    arguments: str | None = field(default=None, repr=False)
    result: dict[str, Any] | None = field(default=None, repr=False)
    is_error: bool | None = None
    error: dict[str, Any] | None = field(default=None, repr=False)
    guard_metadata: dict[str, Any] | None = field(default=None, repr=False)
    barrier: bool = False


@dataclass(frozen=True)
class ToolCall:
    event: Event
    result: Event | None = field(default=None, repr=False)


@dataclass(frozen=True)
class Session:
    session_id: str
    source: str
    version: int
    parent_session: str | None
    events: tuple[Event, ...]
    calls: tuple[ToolCall, ...]
    warnings: tuple[str, ...]
