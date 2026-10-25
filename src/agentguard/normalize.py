"""Projection of the inspected Harness v4 contract, not a full Harness replay engine."""

from typing import Any

from .models import Event, InputError, LoadedSession, Session, ToolCall

# Vocabulary at upstream commit 22ddee3792402c3e70ec5f86a63c3e3e895a2f60.
# Names are protocol facts from core/session/src/known-event-types.ts (MIT).
KNOWN_TYPES = set(
    """
agent-preset/selected agent/inbox/spliced approval/asked approval/decided approval/policy
assistant/attempt assistant/message command/done command/run compaction/end compaction/prune
compaction/start compaction/summary deliverables/presented developer/message
feedback/message-delete feedback/message-put feedback/record goal/change hook/invoked hook/result
image/offload job/registered job/settled llm/retry llm/retry-started model/selection
permission/preset plan/mode request/context request/header sandbox/mode schedule/change
session-log-deepseek/delivery-accepted session/end-seed session/title session/title-llm-request
step/end step/start subagent/catalog subagent/descriptor subagent/model-selection-policy
system/message team/member team/message/delivered team/message/queued team/task todo/write
tool-workflow/agent-end tool-workflow/agent-start tool-workflow/run-end tool-workflow/run-start
tool/call tool/ptc-dispatch tool/ptc-dispatch-start tool/result turn/end turn/start user/message
web/deepseek-search-llm-request working-directory/change workspace/changes
""".split()
)

POSITIONED_TYPES = {
    "turn/start",
    "turn/end",
    "step/start",
    "step/end",
    "tool/call",
    "tool/result",
    "assistant/message",
    "assistant/attempt",
    "system/message",
    "developer/message",
}


def _integer(value: Any, field: str, location: str) -> int | None:
    if value is None:
        return None
    if type(value) is not int or not 0 <= value <= 2**53 - 1:
        raise InputError(f"{location}: {field} must be a non-negative safe integer")
    return value


def _string(value: Any, field: str, location: str) -> str | None:
    if value is not None and (not isinstance(value, str) or not value):
        raise InputError(f"{location}: {field} must be a non-empty string")
    return value


def normalize_session(loaded: LoadedSession) -> Session:
    events: list[Event] = []
    warnings: list[str] = []
    cut = -1
    for row in loaded.rows:
        if (
            row.get("type") == "session/end-seed"
            and isinstance(row.get("data"), dict)
            and row["data"].get("inherited") is True
        ):
            cut = row.get("seq", -1)
    if loaded.is_seeded and (type(cut) is not int or cut < 0):
        raise InputError(f"{loaded.source}: seeded v4 session requires an inherited boundary")
    if not loaded.is_seeded and cut != -1:
        raise InputError(f"{loaded.source}: inherited boundary in an unseeded session")
    turn = step = None
    for index, row in enumerate(loaded.rows):
        location = f"{loaded.source}: event index {index}"
        if type(row.get("seq")) is not int or row["seq"] != index:
            raise InputError(f"{location}: expected contiguous seq starting at 0")
        kind, data = row.get("type"), row.get("data")
        if not isinstance(kind, str):
            raise InputError(f"{location}: expected event type")
        if kind not in KNOWN_TYPES and row.get("ignorable") is not True:
            raise InputError(f"{location}: unknown required event; unsupported semantics")
        if kind not in KNOWN_TYPES:
            data = {}  # An ignorable extension's payload is opaque, including its shape.
        elif not isinstance(data, dict):
            raise InputError(f"{location}: expected object data")
        timestamp = _integer(row.get("time"), "time", location)
        if timestamp is None:
            warnings.append(f"event {index}: timestamp absent")
        explicit_turn = (
            _integer(data.get("turn"), "turn", location) if kind in POSITIONED_TYPES else None
        )
        explicit_step = (
            _integer(data.get("step"), "step", location) if kind in POSITIONED_TYPES else None
        )
        if explicit_turn is not None:
            if explicit_turn != turn:
                step = None
            turn = explicit_turn
        if kind == "turn/start":
            step = None
        if explicit_step is not None:
            step = explicit_step
        source_kind = guard = name = call_id = arguments = None
        result = error = metadata = None
        is_error = None
        if kind == "tool/call":
            name = _string(data.get("name"), "name", location)
            call_id = _string(data.get("callId"), "callId", location)
            arguments = data.get("arguments")
            if arguments is not None and not isinstance(arguments, str):
                raise InputError(f"{location}: arguments must be a raw JSON string")
            if name is None or arguments is None or call_id is None:
                warnings.append(f"event {index}: incomplete tool identity")
        if kind in ("tool/result", "user/message"):
            message = data.get("message") if kind == "tool/result" else data
            if not isinstance(message, dict):
                raise InputError(f"{location}: expected message object")
            source = message.get("source", {})
            if not isinstance(source, dict):
                raise InputError(f"{location}: expected structured message source")
            source_kind = _string(source.get("kind"), "source.kind", location)
            if kind == "user/message" and source_kind == "repeat-tool-reminder":
                guard = source_kind
                metadata = source
            if kind == "tool/result":
                call_id = _string(message.get("toolCallId"), "toolCallId", location)
                source_call_id = _string(source.get("callId"), "source.callId", location)
                if call_id is not None and source_call_id not in (None, call_id):
                    raise InputError(f"{location}: conflicting result call identifiers")
                if call_id is None:
                    warnings.append(f"event {index}: result has no toolCallId; pairing unknown")
                result = message
                is_error = message.get("isError")
                if is_error is not None and type(is_error) is not bool:
                    raise InputError(f"{location}: isError must be boolean")
                error = data.get("error")
                if error is not None and not isinstance(error, dict):
                    raise InputError(f"{location}: error must be an object")
        barrier = (
            kind
            in (
                "session/end-seed",
                "agent/inbox/spliced",
                "tool/ptc-dispatch",
                "tool/ptc-dispatch-start",
            )
            or isinstance(row.get("surfaceOp"), dict)
            or (kind == "user/message" and source_kind in (None, "user"))
        )
        if kind in ("agent/inbox/spliced", "tool/ptc-dispatch", "tool/ptc-dispatch-start"):
            warnings.append(f"event {index}: unsupported behavioral boundary; analysis resets")
        if isinstance(row.get("surfaceOp"), dict):
            warnings.append(f"event {index}: surface replacement; analysis resets")
        events.append(
            Event(
                index,
                timestamp,
                kind,
                turn,
                step,
                index < cut,
                source_kind,
                guard,
                name,
                call_id,
                arguments,
                result,
                is_error,
                error,
                metadata,
                barrier,
            )
        )
        if kind == "step/end":
            step = None
        if kind == "turn/end":
            turn = step = None
    calls: dict[str, Event] = {}
    results: dict[str, Event] = {}
    for event in events:
        if event.kind not in ("tool/call", "tool/result") or event.call_id is None:
            continue
        target = calls if event.kind == "tool/call" else results
        if event.call_id in target:
            raise InputError(
                f"{loaded.source}: event {event.seq}: duplicate call/result identifier"
            )
        target[event.call_id] = event
    for call_id, result_event in results.items():
        call = calls.get(call_id)
        if call is None:
            warnings.append(f"event {result_event.seq}: orphan tool result")
        elif result_event.seq < call.seq:
            raise InputError(f"{loaded.source}: event {result_event.seq}: result precedes call")
    normalized_calls = tuple(
        ToolCall(event, results.get(event.call_id) if event.call_id is not None else None)
        for event in events
        if event.kind == "tool/call"
    )
    return Session(
        loaded.session_id,
        loaded.source,
        loaded.version,
        loaded.parent_session,
        tuple(events),
        normalized_calls,
        tuple(warnings),
    )
