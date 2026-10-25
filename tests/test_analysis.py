import json
from dataclasses import replace

import pytest
from conftest import make_trace

from agentguard.analyzer import analyze_session, analyze_sessions
from agentguard.jsonutil import canonical_arguments
from agentguard.loader import load_sessions
from agentguard.models import InputError
from agentguard.normalize import normalize_session


def analyzed(trace_file, rows, window=5):
    session = normalize_session(load_sessions(trace_file(rows))[0])
    return analyze_session(session, window)


def test_exact_repeats_nested_key_order_and_different_arguments(trace_file):
    rows = make_trace(
        [
            ("read", '{"path":"x","options":{"a":1,"b":[2,3]}}'),
            ("read", '{"options":{"b":[2,3],"a":1},"path":"x"}'),
            ("read", '{"path":"y"}'),
            ("write", '{"path":"y"}'),
            ("read", '{"path":"x","options":{"a":1,"b":[2,3]}}'),
        ]
    )
    report = analyzed(trace_file, rows)
    assert report["summary"]["exact_repeats"] == 1
    assert report["repetitions"][0]["streak_length"] == 2
    assert report["repetitions"][0]["possible_loop"] is False
    assert report["summary"]["verified_lack_of_progress"] is None


def test_canonical_argument_fallback_and_types():
    assert canonical_arguments('{"b":2,"a":1}') == canonical_arguments('{"a":1,"b":2}')
    assert canonical_arguments("broken") == ("raw", "broken")
    assert canonical_arguments("broken") != canonical_arguments("broken ")
    assert canonical_arguments('"broken"') != canonical_arguments("broken")
    assert canonical_arguments("1") != canonical_arguments('["number","1"]')
    assert canonical_arguments("true") != canonical_arguments("1")
    assert canonical_arguments("1.0") != canonical_arguments("1")
    assert canonical_arguments('{"a":1,"a":2}')[0] == "raw"
    assert canonical_arguments("NaN")[0] == "raw"
    assert canonical_arguments("9007199254740993") != canonical_arguments("9007199254740992")


@pytest.mark.parametrize(
    "next_call,expected",
    [
        (("read", '{"path":"x"}'), "IGNORED"),
        (("read", '{"path":"y"}'), "CHANGED"),
        (("write", '{"path":"x"}'), "CHANGED"),
    ],
)
def test_guard_and_reaction(trace_file, next_call, expected):
    rows = make_trace([("read", '{"path":"x"}')] * 3 + [next_call], guard_after=3)
    report = analyzed(trace_file, rows)
    (reminder,) = report["reminders"]
    assert reminder["guard_name"] == "repeat-tool-reminder"
    assert reminder["reaction"] == expected
    assert reminder["trigger_attribution"] == "inferred_unique_previous_step"
    assert reminder["recovered"] is None
    assert reminder["window_complete"] is False
    assert reminder["following_calls"][0]["is_error"] is False
    assert report["summary"]["task_success"] is None


def test_full_window_and_mixed_reactions(trace_file):
    rows = make_trace([("read", "{}")] * 4 + [("write", "{}")] * 2, guard_after=3)
    reminder = analyzed(trace_file, rows, window=2)["reminders"][0]
    assert reminder["reaction"] == "IGNORED"
    assert [call["reaction"] for call in reminder["following_calls"]] == ["IGNORED", "CHANGED"]
    assert reminder["window_complete"] is True
    assert reminder["window_stop_reason"] == "window_limit"


def test_guard_requires_structured_source_not_text(trace_file):
    rows = make_trace([("read", '{"repeat-tool-reminder":"example"}')])
    for row in rows:
        if row["type"] == "user/message":
            row["data"]["content"] = [{"type": "text", "text": "repeat-tool-reminder"}]
    assert analyzed(trace_file, rows)["summary"]["guard_reminders"] == 0


def test_guard_without_following_call_is_unknown(trace_file):
    rows = make_trace([("read", "{}")] * 4, guard_after=3)
    guard_index = next(
        i
        for i, row in enumerate(rows)
        if row.get("data", {}).get("source", {}).get("kind") == "repeat-tool-reminder"
    )
    reminder = analyzed(trace_file, rows[: guard_index + 1])["reminders"][0]
    assert reminder["reaction"] == "UNKNOWN"
    assert reminder["following_calls"] == []


def test_nonadjacent_out_of_order_results_pair_by_identifier(trace_file):
    rows = make_trace([("read", "{}"), ("write", "{}")])
    results = [row for row in rows if row["type"] == "tool/result"]
    rows = [row for row in rows if row["type"] != "tool/result"] + list(reversed(results))
    for index, row in enumerate(rows[1:]):
        row["seq"] = index
    session = normalize_session(load_sessions(trace_file(rows))[0])
    assert [call.result.call_id for call in session.calls] == ["call-1", "call-2"]
    assert session.calls[0].result.seq > session.calls[1].result.seq


def test_missing_result_interrupted_session(trace_file):
    report = analyzed(trace_file, make_trace([("read", "{}")], interrupted=True))
    assert report["summary"]["missing_tool_results"] == 1
    assert report["tool_calls"][0]["result_seq"] is None
    assert report["tool_calls"][0]["is_error"] is None
    assert report["open_turns_at_end"] == [1]


def test_missing_optional_and_incomplete_fields(trace_file):
    rows = make_trace([("read", "{}")])
    for row in rows[1:]:
        row.pop("time", None)
        if row["type"] == "tool/call":
            row["data"].pop("arguments")
            row["data"].pop("turn")
            row["data"].pop("step")
        if row["type"] == "tool/result":
            row["data"]["message"].pop("isError")
    report = analyzed(trace_file, rows)
    assert report["tool_calls"][0]["action_id"] is None
    assert report["tool_calls"][0]["turn"] == 1
    assert report["tool_calls"][0]["timestamp_ms"] is None
    assert report["tool_calls"][0]["is_error"] is None
    assert report["warnings"]


def test_human_prompt_resets_repetition_and_window(trace_file):
    rows = make_trace([("read", "{}")] * 5, guard_after=3)
    call = [row for row in rows if row["type"] == "tool/call"][3]
    insertion = rows.index(call)
    rows.insert(
        insertion,
        {
            "type": "user/message",
            "time": 999,
            "data": {
                "role": "user",
                "id": "new-user",
                "source": {"kind": "user"},
                "content": [],
            },
            "surfaceOp": "append",
        },
    )
    for index, row in enumerate(rows[1:]):
        row["seq"] = index
    report = analyzed(trace_file, rows)
    assert report["summary"]["exact_repeats"] == 3  # two before prompt, one after
    assert report["reminders"][0]["reaction"] == "UNKNOWN"
    assert report["reminders"][0]["window_stop_reason"] == "behavioral_boundary"


def test_no_cross_session_repetition(trace_file):
    loaded = load_sessions(trace_file(make_trace([("read", "{}")])))[0]
    session = normalize_session(loaded)
    report = analyze_sessions((session, replace(session, session_id="another-session")))
    assert report["summary"]["tool_calls"] == 2
    assert report["summary"]["exact_repeats"] == 0


def test_ambiguous_previous_batch_unknown(trace_file):
    rows = make_trace([("read", "{}")] * 3 + [("write", "{}"), ("read", "{}")], guard_after=4)
    # Put the last two preceding actions in one model tool batch.
    for row in rows:
        if row.get("data", {}).get("step") == 4:
            row["data"]["step"] = 3
    report = analyzed(trace_file, rows)
    assert report["reminders"][0]["reaction"] == "UNKNOWN"
    assert report["reminders"][0]["trigger_call_seq"] is None
    assert len(report["reminders"][0]["preceding_step_call_seqs"]) == 2


def test_inherited_prefix_excluded(trace_file):
    rows = make_trace([("read", "{}")] * 3)
    rows[0]["isSeeded"] = True
    rows[0]["parentSession"] = "synthetic-parent"
    cut = len(rows) - 1
    rows.append({"type": "session/end-seed", "seq": cut, "time": 100, "data": {"inherited": True}})
    report = analyzed(trace_file, rows)
    assert report["summary"]["inherited_events"] == cut
    assert report["summary"]["tool_calls"] == 0
    assert report["summary"]["exact_repeats"] == 0


def test_seed_without_cut_refused(trace_file):
    rows = make_trace([])
    rows[0]["isSeeded"] = True
    with pytest.raises(InputError, match="inherited boundary"):
        analyzed(trace_file, rows)


@pytest.mark.parametrize("kind,ignorable", [("future/required", False), ("future/info", True)])
def test_unknown_events(trace_file, kind, ignorable):
    rows = make_trace([])
    rows.append(
        {"type": kind, "seq": len(rows) - 1, "time": 99, "data": {}, "ignorable": ignorable}
    )
    if ignorable:
        assert analyzed(trace_file, rows)["summary"]["guard_reminders"] == 0
    else:
        with pytest.raises(InputError, match="unknown required event"):
            analyzed(trace_file, rows)


def test_error_metadata_is_observation_not_task_verdict(trace_file):
    rows = make_trace([("bash", '{"command":"run-tests"}')])
    result = next(row for row in rows if row["type"] == "tool/result")
    result["data"]["message"]["isError"] = True
    result["data"]["error"] = {"name": "SyntheticError", "code": "DENIED"}
    report = analyzed(trace_file, rows)
    assert report["tool_calls"][0]["is_error"] is True
    assert report["summary"]["task_success"] is None
    assert "DENIED" not in json.dumps(report)


def test_missing_preceding_result_prevents_attribution(trace_file):
    rows = make_trace([("read", "{}")] * 4, guard_after=3)
    rows = [
        row
        for row in rows
        if not (row["type"] == "tool/result" and row["data"]["message"]["toolCallId"] == "call-3")
    ]
    for index, row in enumerate(rows[1:]):
        row["seq"] = index
    report = analyzed(trace_file, rows)
    assert report["reminders"][0]["reaction"] == "UNKNOWN"
    assert report["summary"]["missing_tool_results"] == 1


def test_next_reminder_ends_first_window(trace_file):
    rows = make_trace([("read", "{}")] * 6, guard_after=3)
    reminder = next(
        row
        for row in rows
        if row.get("data", {}).get("source", {}).get("kind") == "repeat-tool-reminder"
    )
    next_start = next(
        i for i, row in enumerate(rows) if row["type"] == "step/start" and row["data"]["step"] == 6
    )
    second = json.loads(json.dumps(reminder))
    second["data"]["id"] = "second-reminder"
    rows.insert(next_start + 1, second)
    for index, row in enumerate(rows[1:]):
        row["seq"] = index
    first, second = analyzed(trace_file, rows)["reminders"]
    assert first["window_observed"] == 2
    assert first["window_stop_reason"] == "next_reminder"
    assert second["window_observed"] == 1


@pytest.mark.parametrize(
    "boundary", ["session/end-seed", "agent/inbox/spliced", "tool/ptc-dispatch"]
)
def test_boundary_does_not_launder_repetitions(trace_file, boundary):
    rows = make_trace([("read", "{}")] * 2)
    call = [row for row in rows if row["type"] == "tool/call"][-1]
    rows.insert(rows.index(call), {"type": boundary, "data": {}, "time": 99})
    for index, row in enumerate(rows[1:]):
        row["seq"] = index
    assert analyzed(trace_file, rows)["summary"]["exact_repeats"] == 0


@pytest.mark.parametrize("defect", ["duplicate_call", "conflicting_result_source", "bad_seed_data"])
def test_ambiguous_or_malformed_records_refused(trace_file, defect):
    rows = make_trace([("read", "{}"), ("write", "{}")])
    if defect == "duplicate_call":
        calls = [row for row in rows if row["type"] == "tool/call"]
        calls[1]["data"]["callId"] = calls[0]["data"]["callId"]
        calls[1]["data"]["step"] = calls[0]["data"]["step"]
    elif defect == "conflicting_result_source":
        result = next(row for row in rows if row["type"] == "tool/result")
        result["data"]["message"]["source"]["callId"] = "unrelated"
    else:
        rows.append({"type": "session/end-seed", "seq": len(rows) - 1, "time": 9, "data": []})
    with pytest.raises(InputError):
        analyzed(trace_file, rows)


def test_orphan_result_kept_as_warning(trace_file):
    rows = make_trace([("read", "{}")])
    result = next(row for row in rows if row["type"] == "tool/result")
    result["data"]["message"]["toolCallId"] = "orphan"
    result["data"]["message"]["source"]["callId"] = "orphan"
    report = analyzed(trace_file, rows)
    assert report["summary"]["missing_tool_results"] == 1
    assert any("orphan tool result" in warning for warning in report["warnings"])


def test_surface_replacement_stops_observation(trace_file):
    rows = make_trace([("read", "{}")] * 4, guard_after=3)
    reminder = next(
        row
        for row in rows
        if row.get("data", {}).get("source", {}).get("kind") == "repeat-tool-reminder"
    )
    reminder["surfaceOp"] = {"op": "replace", "startSeq": 3, "endSeq": 3}
    reminder["sourceEventSeqs"] = [3]
    report = analyzed(trace_file, rows)
    assert report["reminders"][0]["reaction"] == "UNKNOWN"
    assert report["reminders"][0]["following_calls"] == []
    assert any("surface replacement" in warning for warning in report["warnings"])


@pytest.mark.parametrize("data", [[1, 2], {"turn": "opaque", "step": ["opaque"]}])
def test_unknown_ignorable_payload_remains_opaque(trace_file, data):
    rows = make_trace([])
    rows.append(
        {"type": "external/info", "seq": len(rows) - 1, "time": 99, "ignorable": True, "data": data}
    )
    assert analyzed(trace_file, rows)["summary"]["tool_calls"] == 0
