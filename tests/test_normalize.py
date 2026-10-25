"""Regression cases checked against Harness's scoped tool lifecycle contract."""

from copy import deepcopy

import pytest
from conftest import make_trace

from agentguard.analyzer import analyze_session
from agentguard.loader import load_sessions
from agentguard.models import InputError
from agentguard.normalize import normalize_session


def normalized(trace_file, rows):
    return normalize_session(load_sessions(trace_file(rows))[0])


def renumber(rows):
    for seq, row in enumerate(rows[1:]):
        row["seq"] = seq
    return rows


def test_reused_call_id_in_different_steps(trace_file):
    rows = make_trace([("read", "{}"), ("write", "{}")])
    for row in rows:
        if row["type"] == "assistant/message":
            row["data"]["message"]["content"][0]["id"] = "reused-id"
        if row["type"] == "tool/call":
            row["data"]["callId"] = "reused-id"
        if row["type"] == "tool/result":
            message = row["data"]["message"]
            message["toolCallId"] = message["source"]["callId"] = "reused-id"
    session = normalized(trace_file, rows)
    assert [call.result.step for call in session.calls] == [1, 2]
    assert [call.result.seq for call in session.calls] == [7, 12]


def test_result_cannot_pair_across_steps(trace_file):
    rows = make_trace([("read", "{}")])
    result = next(row for row in rows if row["type"] == "tool/result")
    result["data"]["step"] = 2
    with pytest.raises(InputError, match="coordinates"):
        normalized(trace_file, rows)


def test_result_cannot_cite_a_different_call(trace_file):
    rows = make_trace([("read", "{}"), ("write", "{}")])
    calls = [row for row in rows if row["type"] == "tool/call"]
    result = [row for row in rows if row["type"] == "tool/result"][-1]
    result["sourceEventSeqs"] = [calls[0]["seq"]]
    with pytest.raises(InputError, match="source"):
        normalized(trace_file, rows)


def test_replacement_result_is_not_a_second_execution(trace_file):
    rows = make_trace([("read", "{}")])
    original = next(row for row in rows if row["type"] == "tool/result")
    replacement = deepcopy(original)
    replacement["data"]["message"]["id"] = "replacement-result"
    replacement["data"]["message"]["isError"] = True
    replacement["surfaceOp"] = {
        "op": "replace",
        "startSeq": original["seq"],
        "endSeq": original["seq"],
    }
    replacement["sourceEventSeqs"] = [original["seq"]]
    rows.insert(-1, replacement)
    session = normalized(trace_file, renumber(rows))
    assert session.calls[0].result.seq == original["seq"]
    assert session.calls[0].result.is_error is False
    assert analyze_session(session)["summary"]["missing_tool_results"] == 0


def test_historical_result_does_not_change_active_step(trace_file):
    rows = make_trace([("read", "{}"), ("write", "{}")])
    original = next(row for row in rows if row["type"] == "tool/result")
    replacement = deepcopy(original)
    replacement["data"]["message"]["id"] = "replacement"
    replacement["surfaceOp"] = {
        "op": "replace",
        "startSeq": original["seq"],
        "endSeq": original["seq"],
    }
    replacement["sourceEventSeqs"] = [original["seq"]]
    next_step = next(
        i for i, row in enumerate(rows) if row["type"] == "step/start" and row["data"]["step"] == 2
    )
    context = {
        "type": "user/message",
        "time": 99,
        "surfaceOp": "append",
        "data": {
            "id": "context",
            "role": "user",
            "content": [],
            "source": {"kind": "repeat-tool-reminder"},
        },
    }
    rows[next_step + 1 : next_step + 1] = [replacement, context]
    session = normalized(trace_file, renumber(rows))
    reminder = next(event for event in session.events if event.guard_name)
    assert (reminder.turn, reminder.step) == (1, 2)


@pytest.mark.parametrize("defect", ["result_role", "result_source", "guard_role", "error_flag"])
def test_contradictory_message_discriminators_refused(trace_file, defect):
    rows = make_trace([("read", "{}")] * 4, guard_after=3)
    result = next(row for row in rows if row["type"] == "tool/result")
    reminder = next(
        row
        for row in rows
        if row.get("data", {}).get("source", {}).get("kind") == "repeat-tool-reminder"
    )
    if defect == "result_role":
        result["data"]["message"]["role"] = "user"
    elif defect == "result_source":
        result["data"]["message"]["source"]["kind"] = "user"
    elif defect == "guard_role":
        reminder["data"]["role"] = "tool"
    else:
        result["data"]["error"] = {"name": "SyntheticError", "code": "SYNTHETIC"}
    with pytest.raises(InputError):
        normalized(trace_file, rows)
