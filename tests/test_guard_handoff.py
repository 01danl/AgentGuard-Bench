"""Synthetic regression for the handoff observed in a real Harness runtime probe."""

from copy import deepcopy

import pytest
from conftest import make_trace

from agentguard.analyzer import analyze_session
from agentguard.loader import load_sessions
from agentguard.normalize import normalize_session


def handoff_trace(mode="ignored"):
    next_call = ("read", "{}") if mode != "changed" else ("read", '{"path":"other"}')
    rows = make_trace([("read", "{}")] * 3 + [next_call], guard_after=3)
    admitted = next(row for row in rows if row.get("data", {}).get("id") == "reminder-4")
    step_end = next(
        i for i, row in enumerate(rows) if row["type"] == "step/end" and row["data"]["step"] == 3
    )
    queued = {
        "type": "agent/inbox/spliced",
        "time": 100,
        "data": {"target": "next-step", "start": 0, "inserted": [deepcopy(admitted["data"])]},
    }
    claimed = {
        "type": "agent/inbox/spliced",
        "time": 101,
        "data": {"target": "next-step", "start": 0, "removedCount": 1, "inserted": []},
    }
    rows.insert(step_end, queued)
    rows.insert(step_end + 2, claimed)
    if mode == "unknown":
        rows = rows[: rows.index(admitted) + 1]
    for seq, row in enumerate(rows[1:]):
        row["seq"] = seq
    return rows, queued, claimed, admitted


def report(trace_file, rows):
    session = normalize_session(load_sessions(trace_file(rows))[0])
    return session, analyze_session(session)


@pytest.mark.parametrize(
    "mode,expected_repeats,expected_reaction",
    [
        ("ignored", 3, "IGNORED"),
        ("changed", 2, "CHANGED"),
        ("unknown", 2, "UNKNOWN"),
    ],
)
def test_guard_queue_claim_admission_preserves_observed_context(
    trace_file,
    mode,
    expected_repeats,
    expected_reaction,
):
    rows, queued, claimed, admitted = handoff_trace(mode)
    session, analyzed = report(trace_file, rows)
    assert session.events[queued["seq"]].barrier is False
    assert session.events[claimed["seq"]].barrier is False
    assert analyzed["summary"]["exact_repeats"] == expected_repeats
    assert analyzed["summary"]["guard_reminders"] == 1  # Queue entry is not a second warning.
    (reminder,) = analyzed["reminders"]
    assert reminder["event_seq"] == admitted["seq"]
    assert reminder["trigger_attribution"] == "inferred_unique_previous_step"
    assert reminder["reaction"] == expected_reaction
    assert reminder["recovered"] is None


@pytest.mark.parametrize(
    "defect",
    [
        "canceled",
        "different_payload",
        "missing_admission",
        "next_turn",
        "invalid_start",
        "mixed_user_input",
        "different_message_id",
    ],
)
def test_unverified_inbox_edits_remain_boundaries(trace_file, defect):
    rows, queued, claimed, admitted = handoff_trace()
    if defect == "canceled":
        claimed["data"]["outcome"] = "canceled"
    elif defect == "different_payload":
        admitted["data"]["content"] = [{"type": "text", "text": "Changed payload"}]
    elif defect == "missing_admission":
        admitted["data"]["source"] = {"kind": "runtime-context"}
    elif defect == "next_turn":
        queued["data"]["target"] = claimed["data"]["target"] = "next-turn"
    elif defect == "invalid_start":
        queued["data"]["start"] = 2
    elif defect == "mixed_user_input":
        human = {"id": "queued-human", "role": "user", "content": [], "source": {"kind": "user"}}
        queued["data"]["inserted"].append(human)
        claimed["data"]["removedCount"] = 2
    else:
        admitted["data"]["id"] = "not-the-queued-message"
    session, analyzed = report(trace_file, rows)
    assert session.events[queued["seq"]].barrier is True
    assert session.events[claimed["seq"]].barrier is True
    assert any("unsupported behavioral boundary" in warning for warning in session.warnings)
    assert all(reminder["reaction"] == "UNKNOWN" for reminder in analyzed["reminders"])


def test_multiple_guard_notices_are_counted_only_on_admission(trace_file):
    rows, queued, claimed, admitted = handoff_trace()
    second = deepcopy(admitted)
    second["data"]["id"] = "second-synthetic-reminder"
    queued["data"]["inserted"].append(deepcopy(second["data"]))
    claimed["data"]["removedCount"] = 2
    rows.insert(rows.index(admitted) + 1, second)
    for seq, row in enumerate(rows[1:]):
        row["seq"] = seq
    session, analyzed = report(trace_file, rows)
    assert session.events[queued["seq"]].barrier is False
    assert session.events[claimed["seq"]].barrier is False
    assert analyzed["summary"]["guard_reminders"] == 2
    assert [item["reaction"] for item in analyzed["reminders"]] == ["UNKNOWN", "IGNORED"]


def test_duplicate_queued_message_ids_are_not_a_verified_handoff(trace_file):
    rows, queued, claimed, admitted = handoff_trace()
    queued["data"]["inserted"].append(deepcopy(queued["data"]["inserted"][0]))
    claimed["data"]["removedCount"] = 2
    rows.insert(rows.index(admitted) + 1, deepcopy(admitted))
    for seq, row in enumerate(rows[1:]):
        row["seq"] = seq
    session, _ = report(trace_file, rows)
    assert session.events[queued["seq"]].barrier is True
    assert session.events[claimed["seq"]].barrier is True
