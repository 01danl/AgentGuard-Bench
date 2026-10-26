"""Projection of the inspected Harness v4 contract, not a full Harness replay engine."""

from collections import defaultdict
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
    guard_handoffs = _guard_handoff_splices(loaded.rows)
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
        if kind == "turn/start":
            turn = explicit_turn
            step = None
        if kind == "step/start":
            if explicit_turn is not None:
                turn = explicit_turn
            step = explicit_step
        event_turn = explicit_turn if explicit_turn is not None else turn
        event_step = (
            explicit_step if explicit_step is not None else (step if event_turn == turn else None)
        )
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
            if source_kind == "plugin":
                raise InputError(
                    f"{location}: retired plugin source is invalid in v4; "
                    "re-export with current Harness"
                )
            expected_role = "tool" if kind == "tool/result" else "user"
            if message.get("role") not in (None, expected_role):
                raise InputError(f"{location}: conflicting message role")
            if kind == "user/message" and source_kind == "repeat-tool-reminder":
                guard = source_kind
                metadata = source
            if kind == "tool/result":
                if source_kind not in (None, "tool"):
                    raise InputError(f"{location}: conflicting tool result source")
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
                if error is not None and is_error is not True:
                    raise InputError(f"{location}: error metadata requires isError=true")
        unsupported_boundary = kind in ("tool/ptc-dispatch", "tool/ptc-dispatch-start") or (
            kind == "agent/inbox/spliced" and index not in guard_handoffs
        )
        barrier = (
            kind == "session/end-seed"
            or unsupported_boundary
            or isinstance(row.get("surfaceOp"), dict)
            or (kind == "user/message" and source_kind in (None, "user"))
        )
        if unsupported_boundary:
            warnings.append(f"event {index}: unsupported behavioral boundary; analysis resets")
        if isinstance(row.get("surfaceOp"), dict):
            warnings.append(f"event {index}: surface replacement; analysis resets")
        events.append(
            Event(
                index,
                timestamp,
                kind,
                event_turn,
                event_step,
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
        if kind == "step/end" and (event_turn, event_step) == (turn, step):
            step = None
        if kind == "turn/end" and event_turn == turn:
            turn = step = None
    normalized_calls = _pair_calls(events, loaded, warnings)
    return Session(
        loaded.session_id,
        loaded.source,
        loaded.version,
        loaded.parent_session,
        tuple(events),
        normalized_calls,
        tuple(warnings),
    )


def _guard_handoff_splices(rows: tuple[dict[str, Any], ...]) -> set[int]:
    """Recognize only verified guard-only next-step enqueue/claim/admission paths.

    Harness logs queue edits before entering the same UserMessage in the next step.
    These records neither introduce human input nor represent additional reminders.
    Cancellation, mixed edits, invalid queue coordinates or unobserved delivery remain
    opaque boundaries. This is not a general inbox or model-surface interpreter.
    """
    queue: list[tuple[int | None, dict[str, Any]]] | None = []
    transparent: set[int] = set()
    for index, row in enumerate(rows):
        if row.get("type") != "agent/inbox/spliced":
            continue
        data = row.get("data")
        if not isinstance(data, dict) or data.get("target") != "next-step" or queue is None:
            continue
        start, count, inserted = (
            data.get("start"),
            data.get("removedCount", 0),
            data.get("inserted"),
        )
        if (
            type(start) is not int
            or type(count) is not int
            or not 0 <= start <= len(queue)
            or not 0 <= count <= len(queue) - start
            or not isinstance(inserted, list)
            or not all(isinstance(m, dict) for m in inserted)
        ):
            queue = None
            continue
        guard_append = (
            start == len(queue)
            and count == 0
            and "outcome" not in data
            and all(
                isinstance(m.get("id"), str)
                and bool(m["id"])
                and m.get("role") == "user"
                and isinstance(m.get("content"), list)
                and isinstance(m.get("source"), dict)
                and m["source"].get("kind") == "repeat-tool-reminder"
                for m in inserted
            )
        )
        removed = queue[start : start + count]
        claimed_guards = (
            start == 0
            and count == len(queue)
            and count > 0
            and not inserted
            and "outcome" not in data
            and all(origin is not None for origin, _ in removed)
            and len({message["id"] for _, message in removed}) == len(removed)
        )
        queue = (
            queue[:start]
            + [(index if guard_append else None, m) for m in inserted]
            + queue[start + count :]
        )
        if not claimed_guards:
            continue
        entered = False
        matched = 0
        for lookahead in range(index + 1, len(rows)):
            future = rows[lookahead]
            kind = future.get("type")
            if kind == "step/start":
                if entered:
                    break
                entered = True
            elif kind in (
                "assistant/message",
                "assistant/attempt",
                "tool/call",
                "step/end",
                "turn/end",
                "agent/inbox/spliced",
                "session/end-seed",
            ):
                break
            elif (
                entered
                and kind == "user/message"
                and future.get("surfaceOp") == "append"
                and future.get("data") == removed[matched][1]
            ):
                matched += 1
                if matched == len(removed):
                    transparent.add(index)
                    transparent.update(origin for origin, _ in removed if origin is not None)
                    break
    return transparent


def _pair_calls(
    events: list[Event],
    loaded: LoadedSession,
    warnings: list[str],
) -> tuple[ToolCall, ...]:
    # Provider call IDs can recur after settlement in another step. They are not
    # session-global identities. Durable source references are stronger evidence.
    scoped: dict[tuple[int | None, int | None, str], Event] = {}
    by_id: dict[str, list[Event]] = defaultdict(list)
    by_seq: dict[int, Event] = {}
    results: dict[int, Event] = {}
    for event in events:
        if event.kind != "tool/call" or event.call_id is None:
            continue
        key = (event.turn, event.step, event.call_id)
        if key in scoped:
            raise InputError(f"{loaded.source}: event {event.seq}: duplicate call ID in one step")
        scoped[key] = event
        by_id[event.call_id].append(event)
        by_seq[event.seq] = event
    for event in events:
        if event.kind != "tool/result" or event.call_id is None:
            continue
        location = f"{loaded.source}: event {event.seq}"
        row = loaded.rows[event.seq]
        if isinstance(row.get("surfaceOp"), dict):
            continue  # A rewritten presentation node is not another execution result.
        refs = row.get("sourceEventSeqs", [])
        if not isinstance(refs, list) or any(
            type(seq) is not int or not 0 <= seq < event.seq for seq in refs
        ):
            raise InputError(f"{location}: invalid result source references")
        cited = [by_seq[seq] for seq in set(refs) if seq in by_seq]
        if len(cited) > 1 or (cited and cited[0].call_id != event.call_id):
            raise InputError(f"{location}: conflicting result source call")
        call = cited[0] if cited else scoped.get((event.turn, event.step, event.call_id))
        if call is None:
            candidates = [
                candidate
                for candidate in by_id[event.call_id]
                if all(
                    left is None or right is None or left == right
                    for left, right in ((candidate.turn, event.turn), (candidate.step, event.step))
                )
            ]
            if len(candidates) > 1:
                raise InputError(f"{location}: ambiguous result coordinates")
            call = candidates[0] if candidates else None
            if call is None and by_id[event.call_id]:
                raise InputError(f"{location}: conflicting result coordinates")
        if call is None:
            warnings.append(f"event {event.seq}: orphan tool result")
            continue
        if any(
            left is not None and right is not None and left != right
            for left, right in (
                (call.turn, event.turn),
                (call.step, event.step),
            )
        ):
            raise InputError(f"{location}: conflicting result coordinates")
        if event.seq < call.seq:
            raise InputError(f"{location}: result precedes call")
        if call.seq in results:
            raise InputError(f"{location}: duplicate result for one tool call")
        results[call.seq] = event
    return tuple(
        ToolCall(event, results.get(event.seq)) for event in events if event.kind == "tool/call"
    )
