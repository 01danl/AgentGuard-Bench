"""Conservative observations over a log. CHANGED never means RECOVERED."""

from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from typing import Any

from .jsonutil import canonical_arguments
from .models import Event, Session, ToolCall


def analyze_session(session: Session, window: int = 5) -> dict[str, Any]:
    if type(window) is not int or window < 1:
        raise ValueError("window must be a positive integer")
    live_calls = [call for call in session.calls if not call.event.inherited]
    call_seqs = [call.event.seq for call in live_calls]
    by_seq = {call.event.seq: call for call in live_calls}
    step_calls: dict[tuple[int | None, int | None], list[ToolCall]] = defaultdict(list)
    step_ends: dict[tuple[int | None, int | None], list[int]] = defaultdict(list)
    for call in live_calls:
        step_calls[(call.event.turn, call.event.step)].append(call)
    for event in session.events:
        if event.kind == "step/end" and not event.inherited:
            step_ends[(event.turn, event.step)].append(event.seq)
    # Prefix indexes keep reminder analysis bounded even for large parallel batches.
    step_indexes = {}
    for key, calls in step_calls.items():
        missing = [0]
        result_max = [-1]
        for call in calls:
            missing.append(missing[-1] + (call.result is None))
            result_max.append(max(result_max[-1], call.result.seq if call.result else -1))
        step_indexes[key] = ([call.event.seq for call in calls], missing, result_max)
    identities: dict[int, tuple[str, tuple[str, str]] | None] = {}
    action_ids: dict[tuple[str, tuple[str, str]], str] = {}
    evidence: dict[int, dict[str, Any]] = {}
    for call in live_calls:
        event = call.event
        identity = None
        mode = None
        if event.tool_name is not None and event.arguments is not None:
            canonical = canonical_arguments(event.arguments)
            mode = canonical[0]
            identity = (event.tool_name, canonical)
            action_ids.setdefault(identity, f"action_{len(action_ids) + 1:04d}")
        identities[event.seq] = identity
        evidence[event.seq] = {
            "seq": event.seq,
            "timestamp_ms": event.timestamp_ms,
            "turn": event.turn,
            "step": event.step,
            "tool_name": event.tool_name,
            "call_id": event.call_id,
            "action_id": action_ids.get(identity),
            "argument_mode": mode,
            "result_seq": call.result.seq if call.result else None,
            "is_error": call.result.is_error if call.result else None,
            "has_error_metadata": call.result.error is not None if call.result else None,
        }

    repeats = []
    previous: Event | None = None
    streak = 0
    streak_at: dict[int, int] = {}
    boundaries: list[int] = []
    guards: list[Event] = []
    for event in session.events:
        if event.inherited:
            continue
        if event.barrier:
            previous = None
            streak = 0
            boundaries.append(event.seq)
        if event.guard_name is not None:
            guards.append(event)
        if event.seq not in by_seq:
            continue
        identity = identities[event.seq]
        if previous is not None and identity is not None and identities[previous.seq] == identity:
            streak += 1
            repeats.append(
                {
                    "previous_seq": previous.seq,
                    "seq": event.seq,
                    "streak_length": streak,
                    "action_id": evidence[event.seq]["action_id"],
                    "observation": "repeated_call",
                    "possible_loop": streak >= 3,
                    "verified_lack_of_progress": None,
                }
            )
        else:
            streak = 1
        streak_at[event.seq] = streak
        previous = event

    reactions = []
    for guard_index, guard in enumerate(guards):
        boundary_index = bisect_right(boundaries, guard.seq)
        boundary_before = boundaries[boundary_index - 1] if boundary_index else -1
        preceding_index = bisect_left(call_seqs, guard.seq) - 1
        candidates: list[ToolCall] = []
        candidate_count = 0
        baseline: ToolCall | None = None
        if preceding_index >= 0 and call_seqs[preceding_index] > boundary_before:
            last = live_calls[preceding_index].event
            key = (last.turn, last.step)
            group = step_calls[key]
            seqs, missing, result_max = step_indexes[key]
            start = bisect_right(seqs, boundary_before)
            end = bisect_left(seqs, guard.seq)
            if last.turn is not None and last.step is not None:
                candidate_count = end - start
                candidates = group[start : min(end, start + 20)]
            # Reminders are queued for the next step, after an executed tool batch.
            # Require one observed action identity in that batch and a repeated streak.
            ends = step_ends[key]
            closed = bisect_left(ends, guard.seq) > bisect_right(ends, last.seq)
            if (
                candidate_count
                and identities[last.seq] is not None
                and streak_at[last.seq] >= max(2, candidate_count)
                and closed
                and missing[end] == missing[start]
                and result_max[end] < guard.seq
                and (guard.turn, guard.step) != (last.turn, last.step)
            ):
                baseline = live_calls[preceding_index]

        stop = len(session.events)
        stop_reason = "end_of_log"
        if guard_index + 1 < len(guards):
            stop = guards[guard_index + 1].seq
            stop_reason = "next_reminder"
        next_boundary = boundaries[boundary_index] if boundary_index < len(boundaries) else None
        if guard.seq == boundary_before:
            next_boundary = guard.seq
        if next_boundary is not None and next_boundary < stop:
            stop = next_boundary
            stop_reason = "behavioral_boundary"
        first = bisect_right(call_seqs, guard.seq)
        last_index = min(bisect_left(call_seqs, stop), first + window)
        following = live_calls[first:last_index]
        observations = []
        for call in following:
            reaction = "UNKNOWN"
            if baseline is not None and identities[call.event.seq] is not None:
                reaction = (
                    "IGNORED"
                    if identities[call.event.seq] == identities[baseline.event.seq]
                    else "CHANGED"
                )
            observations.append({**evidence[call.event.seq], "reaction": reaction})
        reactions.append(
            {
                "session_id": session.session_id,
                "event_seq": guard.seq,
                "timestamp_ms": guard.timestamp_ms,
                "turn": guard.turn,
                "step": guard.step,
                "guard_name": guard.guard_name,
                "source_form": (guard.guard_metadata or {}).get("form")
                if (guard.guard_metadata or {}).get("form")
                in ("notice", "instructions", "catalog", "snapshot", "relay", "recall")
                else None,
                "trigger_attribution": "inferred_unique_previous_step" if baseline else "unknown",
                "trigger_call_seq": baseline.event.seq if baseline else None,
                "preceding_step_call_seqs": [call.event.seq for call in candidates],
                "preceding_step_call_count": candidate_count,
                "preceding_step_evidence_truncated": candidate_count > len(candidates),
                "reaction": observations[0]["reaction"] if observations else "UNKNOWN",
                "classification_basis": "first_subsequent_call",
                "following_calls": observations,
                "window_observed": len(observations),
                "window_complete": len(observations) == window,
                "window_stop_reason": "window_limit"
                if len(observations) == window
                else stop_reason,
                "recovered": None,
            }
        )
    counts = Counter(reaction["reaction"] for reaction in reactions)
    open_turns: set[int] = set()
    for event in session.events:
        if event.inherited or event.turn is None:
            continue
        if event.kind == "turn/start":
            open_turns.add(event.turn)
        elif event.kind == "turn/end":
            open_turns.discard(event.turn)
    return {
        "session_id": session.session_id,
        "source": session.source,
        "format_version": session.version,
        "parent_session": session.parent_session,
        "summary": {
            "events": len(session.events),
            "inherited_events": sum(event.inherited for event in session.events),
            "tool_calls": len(live_calls),
            "exact_repeats": len(repeats),
            "guard_reminders": len(reactions),
            "missing_tool_results": sum(call.result is None for call in live_calls),
            "reactions": {key: counts[key] for key in ("IGNORED", "CHANGED", "UNKNOWN")},
            "task_success": None,
            "verified_lack_of_progress": None,
        },
        "open_turns_at_end": sorted(open_turns),
        "warnings": list(session.warnings),
        "tool_calls": list(evidence.values()),
        "repetitions": repeats,
        "reminders": reactions,
    }


def analyze_sessions(sessions: tuple[Session, ...], window: int = 5) -> dict[str, Any]:
    reports = [analyze_session(session, window) for session in sessions]
    fields = (
        "events",
        "inherited_events",
        "tool_calls",
        "exact_repeats",
        "guard_reminders",
        "missing_tool_results",
    )
    return {
        "schema_version": "0.1",
        "analyzer_version": "0.1.0",
        "window": window,
        "data_policy": "arguments, results, message text and source summaries omitted",
        "summary": {
            "sessions": len(reports),
            **{field: sum(report["summary"][field] for report in reports) for field in fields},
            "reactions": {
                key: sum(report["summary"]["reactions"][key] for report in reports)
                for key in ("IGNORED", "CHANGED", "UNKNOWN")
            },
            "task_success": None,
            "guard_causal_effect": None,
        },
        "sessions": reports,
        "interpretation": [
            "Repetition is an observation, not proof of an error or lack of progress.",
            "possible_loop is an unvalidated heuristic: at least 3 consecutive identical calls.",
            "Reaction uses the first call; all observed calls in the bounded window are retained.",
            "Trigger attribution is inferred, never an upstream trigger ID.",
            "CHANGED does not imply RECOVERED; is_error=false does not imply task success.",
            "Inherited fork history is counted as events but excluded from behavioral metrics.",
        ],
    }
