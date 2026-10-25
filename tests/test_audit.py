"""Independent metric oracles, cross-session isolation and privacy audit regressions."""

import json
import zipfile
from copy import deepcopy
from dataclasses import replace

import pytest
from conftest import make_trace

from agentguard.analyzer import analyze_session, analyze_sessions
from agentguard.cli import main
from agentguard.jsonutil import canonical_arguments
from agentguard.loader import load_sessions
from agentguard.models import InputError
from agentguard.normalize import normalize_session


def analyze(trace_file, rows, window=5):
    return analyze_session(normalize_session(load_sessions(trace_file(rows))[0]), window)


def test_missing_reminder_coordinates_are_not_evidence_of_another_step(trace_file):
    rows = make_trace([("read", "{}")] * 4, guard_after=3)
    guard_index = next(
        i
        for i, row in enumerate(rows)
        if row.get("data", {}).get("source", {}).get("kind") == "repeat-tool-reminder"
    )
    # The previous step ended; the new step/start was absent in a partial/malformed log.
    rows.pop(guard_index - 1)
    for seq, row in enumerate(rows[1:]):
        row["seq"] = seq
    reminder = analyze(trace_file, rows)["reminders"][0]
    assert reminder["step"] is None
    assert reminder["trigger_attribution"] == "unknown"
    assert reminder["reaction"] == "UNKNOWN"


def test_zip_result_pairing_does_not_cross_sessions(tmp_path):
    parent = make_trace([("read", "{}")], session_id="parent", interrupted=True)
    child = make_trace([("read", "{}")], session_id="child")
    child = [row for row in child if row["type"] != "tool/call"]
    for seq, row in enumerate(child[1:]):
        row["seq"] = seq
    path = tmp_path / "synthetic-export.zip"
    with zipfile.ZipFile(path, "w") as archive:
        for name, rows in [
            ("session.v4.jsonl", parent),
            ("subagents/child/session.v4.jsonl", child),
        ]:
            archive.writestr(name, "\n".join(json.dumps(row) for row in rows))
    sessions = tuple(normalize_session(item) for item in load_sessions(path))
    reports = {item["session_id"]: item for item in analyze_sessions(sessions)["sessions"]}
    assert reports["parent"]["summary"]["missing_tool_results"] == 1
    assert reports["parent"]["tool_calls"][0]["result_seq"] is None
    assert reports["child"]["summary"]["tool_calls"] == 0
    assert any("orphan" in warning for warning in reports["child"]["warnings"])


def test_session_with_no_following_call_cannot_borrow_child_actions(trace_file):
    rows = make_trace([("read", "{}")] * 4, guard_after=3)
    guard_index = next(
        i
        for i, row in enumerate(rows)
        if row.get("data", {}).get("source", {}).get("kind") == "repeat-tool-reminder"
    )
    parent = normalize_session(load_sessions(trace_file(rows[: guard_index + 1]))[0])
    child = normalize_session(
        load_sessions(trace_file(make_trace([("read", "{}")], session_id="child")))[0]
    )
    reports = analyze_sessions((parent, child))["sessions"]
    assert reports[0]["reminders"][0]["reaction"] == "UNKNOWN"
    assert reports[0]["reminders"][0]["following_calls"] == []
    assert reports[1]["summary"]["exact_repeats"] == 0


def test_repeat_count_matches_independent_run_length_oracle(trace_file):
    # Same JSON object represented in different key order still has one identity.
    calls = [
        ("poll", '{"a":1,"b":2}'),
        ("poll", '{"b":2,"a":1}'),
        ("poll", '{"a":1,"b":2}'),
        ("read", "{}"),
        ("read", "{}"),
        ("poll", '{"a":1,"b":2}'),
    ]
    report = analyze(trace_file, make_trace(calls))
    # Runs have lengths 3, 2, 1; repeats = (3-1)+(2-1)+(1-1) = 3.
    assert report["summary"]["exact_repeats"] == 3
    assert [item["streak_length"] for item in report["repetitions"]] == [2, 3, 2]
    assert [item["possible_loop"] for item in report["repetitions"]] == [False, True, False]
    call_seqs = {item["seq"] for item in report["tool_calls"]}
    assert all(
        item["seq"] in call_seqs and item["previous_seq"] in call_seqs
        for item in report["repetitions"]
    )
    assert all(item["verified_lack_of_progress"] is None for item in report["repetitions"])


@pytest.mark.parametrize(
    "left,right,equal",
    [
        ('{"x":[{"a":1,"b":2}]}', '{ "x" : [ {"b":2,"a":1} ] }', True),
        ("[1,2]", "[2,1]", False),
        ('"a b"', '"a  b"', False),
        ('"\\u0061"', '"a"', True),
        ("1", "1.0", False),
        ("0", "-0", False),
        ("true", "1", False),
        ("null", '"null"', False),
        ('{"x":1,"x":2}', '{"x":2}', False),
        ("broken", "broken ", False),
    ],
)
def test_canonical_equivalence_matrix(left, right, equal):
    assert (canonical_arguments(left) == canonical_arguments(right)) is equal


@pytest.mark.parametrize("output_format", ["text", "json"])
def test_zip_cli_never_serializes_sensitive_payloads(tmp_path, capsys, output_format):
    secret = "SYNTHETIC-SECRET-audit-only"
    rows = make_trace([("bash", json.dumps({"api_key": secret}))] * 4, guard_after=3)
    for row in rows:
        if row["type"] == "tool/result":
            row["data"]["meta"] = {"token": secret}
            row["data"]["message"]["content"] = [{"type": "text", "text": secret}]
            row["data"]["message"]["isError"] = True
            row["data"]["error"] = {"name": "SyntheticError", "code": "SYNTHETIC", "reason": secret}
        if row["type"] == "user/message":
            row["data"]["content"] = [{"type": "text", "text": secret}]
            row["data"]["source"]["summary"] = secret
    path = tmp_path / "synthetic-export.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("session.v4.jsonl", "\n".join(json.dumps(row) for row in rows))
        archive.writestr("files/aa/synthetic/secret.jsonl", secret)
    assert main(["analyze", str(path), "--format", output_format]) == 0
    captured = capsys.readouterr()
    assert secret not in captured.out + captured.err


def test_analyzer_does_not_mutate_inputs(trace_file):
    session = normalize_session(
        load_sessions(trace_file(make_trace([("read", "{}")] * 4, guard_after=3)))[0]
    )
    before = deepcopy(session)
    first = analyze_session(session)
    assert first == analyze_session(session)
    assert session == before


def test_aggregate_rejects_duplicate_session_ids(trace_file):
    session = normalize_session(load_sessions(trace_file(make_trace([])))[0])
    with pytest.raises(InputError, match="Duplicate session"):
        analyze_sessions((session, replace(session, source="another-file.jsonl")))


def test_empty_aggregate_still_validates_window():
    with pytest.raises(ValueError, match="positive"):
        analyze_sessions((), window=0)


def test_noncontiguous_step_group_cannot_look_homogeneous(trace_file):
    rows = make_trace(
        [("write", "{}"), ("read", "{}"), ("read", "{}"), ("read", "{}")], guard_after=3
    )
    # This is not a valid Harness lifecycle, but our partial projector accepts it.
    # A streak of two read calls must not hide the earlier write in the same group.
    for row in rows:
        if row.get("data", {}).get("step") == 3:
            row["data"]["step"] = 1
    reminder = analyze(trace_file, rows)["reminders"][0]
    assert reminder["preceding_step_call_count"] == 2
    assert reminder["trigger_attribution"] == "unknown"
    assert reminder["reaction"] == "UNKNOWN"
