"""Bounded JSONL and ZIP input. ZIP members are streamed, never extracted."""

import re
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import BinaryIO
from zlib import error as ZlibError

from .jsonutil import parse_json
from .models import InputError, Limits, LoadedSession


def _read_session(stream: BinaryIO, source: str, limits: Limits) -> LoadedSession:
    rows = []
    consumed = 0
    header = None
    for line_number in range(1, limits.max_events + 3):
        line = stream.readline(limits.max_line_bytes + 1)
        if not line:
            break
        consumed += len(line)
        location = f"{source}: line {line_number}"
        if len(line) > limits.max_line_bytes or consumed > min(
            limits.max_input_bytes, limits.max_total_bytes
        ):
            raise InputError(f"{location}: input or line size limit exceeded")
        if not line.strip():
            continue
        try:
            row = parse_json(line.decode("utf-8"))
        except (UnicodeError, ValueError, RecursionError):
            raise InputError(f"{location}: invalid UTF-8 or JSON (payload omitted)") from None
        if not isinstance(row, dict):
            raise InputError(f"{location}: expected a JSON object")
        if header is None:
            if row.get("type") != "session":
                raise InputError(f"{location}: expected a Harness session header")
            if type(row.get("version")) is not int or row["version"] != 4:
                raise InputError(f"{location}: unsupported session format; only v4 is supported")
            if not isinstance(row.get("id"), str) or not row["id"]:
                raise InputError(f"{location}: session id must be a non-empty string")
            if type(row.get("isSeeded")) is not bool:
                raise InputError(f"{location}: isSeeded must be a boolean in v4")
            for field in ("createdAt", "delegationDepth"):
                value = row.get(field)
                if type(value) is not int or not 0 <= value <= 2**53 - 1:
                    raise InputError(f"{location}: invalid required header field {field}")
            if "parentSession" in row and not isinstance(row["parentSession"], str):
                raise InputError(f"{location}: invalid parentSession")
            header = row
        else:
            if row.get("type") == "session":
                raise InputError(f"{location}: multiple headers; use separate session files")
            rows.append(row)
            if len(rows) > limits.max_events:
                raise InputError(f"{source}: event count limit exceeded")
    else:
        # Also bounds pathological files made mostly of blank lines.
        raise InputError(f"{source}: line count limit exceeded")
    if header is None:
        raise InputError(f"{source}: empty session file")
    return LoadedSession(
        header["id"],
        source,
        header["version"],
        header["isSeeded"],
        header.get("parentSession"),
        tuple(rows),
    )


def _validate_member(info: zipfile.ZipInfo, limits: Limits) -> None:
    name = info.filename
    parts = PurePosixPath(name).parts
    if (
        not name
        or not parts
        or name.startswith("/")
        or "\\" in name
        or ":" in name
        or ".." in parts
        or any(ord(c) < 32 for c in name)
        or stat.S_ISLNK(info.external_attr >> 16)
    ):
        raise InputError("ZIP contains an unsafe path or symbolic link (name omitted)")
    if info.flag_bits & 1:
        raise InputError("Encrypted ZIP members are unsupported")
    if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
        raise InputError("ZIP must use stored or DEFLATE compression")
    if info.file_size > limits.max_total_bytes:
        raise InputError("ZIP member exceeds uncompressed size limit")
    if info.file_size > max(1, info.compress_size) * limits.max_compression_ratio:
        raise InputError("ZIP compression ratio limit exceeded")


def load_sessions(path: str | Path, limits: Limits | None = None) -> tuple[LoadedSession, ...]:
    """Read one input atomically; never return a silently partial set of sessions.

    ZIP attachment trees files/ and media/ are excluded even for .jsonl uploads.
    Multiple log generations with the same header id are refused rather than merged.
    """
    limits = limits or Limits()
    path = Path(path)
    try:
        if not path.is_file():
            raise InputError("Input must be an existing regular JSONL or ZIP file")
        if path.stat().st_size > limits.max_input_bytes:
            raise InputError("Input size limit exceeded")
        if path.suffix.lower() == ".jsonl":
            with path.open("rb") as stream:
                sessions = [_read_session(stream, path.name, limits)]
        elif path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path) as archive:
                members = archive.infolist()
                if len(members) > limits.max_archive_entries:
                    raise InputError("ZIP entry count limit exceeded")
                names: set[str] = set()
                total = 0
                logs = []
                for info in members:
                    _validate_member(info, limits)
                    normalized_name = str(PurePosixPath(info.filename))
                    if normalized_name in names:
                        raise InputError("ZIP contains duplicate member names")
                    names.add(normalized_name)
                    total += info.file_size
                    if total > limits.max_total_bytes:
                        raise InputError("ZIP total uncompressed size limit exceeded")
                    parts = PurePosixPath(info.filename).parts
                    if (
                        not info.is_dir()
                        and info.filename.endswith(".jsonl")
                        and parts[0] not in ("files", "media")
                    ):
                        logs.append(info)
                    elif parts[0] not in ("files", "media") and re.search(
                        r"\.jsonl\.zstd$", info.filename
                    ):
                        raise InputError("Zstandard logs are unsupported; use Harness ZIP export")
                if not logs:
                    raise InputError("ZIP contains no session JSONL logs")
                if len(logs) > limits.max_sessions:
                    raise InputError("Session count limit exceeded")
                sessions = []
                event_count = 0
                for info in sorted(logs, key=lambda item: item.filename):
                    with archive.open(info) as stream:
                        loaded = _read_session(stream, f"{path.name}!{info.filename}", limits)
                    event_count += len(loaded.rows)
                    if event_count > limits.max_events:
                        raise InputError("Total event count limit exceeded")
                    sessions.append(loaded)
        else:
            raise InputError("Expected a .jsonl file or a .zip Harness export")
    except (OSError, zipfile.BadZipFile, EOFError, RuntimeError, NotImplementedError, ZlibError):
        raise InputError("Cannot read input: I/O failure, corrupt or unsupported ZIP") from None
    if len({session.session_id for session in sessions}) != len(sessions):
        raise InputError("Duplicate session IDs; provide one log generation per session")
    if sum(len(session.rows) for session in sessions) > limits.max_events:
        raise InputError("Total event count limit exceeded")
    return tuple(sessions)
