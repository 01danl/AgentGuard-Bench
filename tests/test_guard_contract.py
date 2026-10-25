"""Synthetic regressions pinned to Harness 22ddee3's native V4 source contract."""

import json
from copy import deepcopy

import pytest
from conftest import make_trace

from agentguard.analyzer import analyze_session
from agentguard.cli import main
from agentguard.loader import load_sessions
from agentguard.models import InputError
from agentguard.normalize import normalize_session


@pytest.fixture
def guard_rows():
    rows = make_trace([("read", "{}")] * 3 + [("read", '{"path":"different"}')], guard_after=3)
    event = next(row for row in rows if row.get("data", {}).get("id") == "reminder-4")
    # A literal UserMessage, independently specified from the trace builder.
    # Only the structured producer kind identifies this notice as a guard.
    event["data"] = {
        "id": "synthetic-official-reminder",
        "role": "user",
        "source": {
            "kind": "repeat-tool-reminder",
            "form": "notice",
            "summary": "read × 3",
        },
        "content": [{"type": "text", "text": "Synthetic advisory notice."}],
    }
    return rows, event


def test_official_v4_flat_source_is_detected(trace_file, guard_rows):
    rows, original = guard_rows
    session = normalize_session(load_sessions(trace_file(rows))[0])
    event = next(event for event in session.events if event.guard_name)
    assert event.seq == original["seq"]
    assert event.kind == "user/message"
    assert event.source_kind == event.guard_name == "repeat-tool-reminder"
    assert event.guard_metadata == original["data"]["source"]
    report = analyze_session(session)
    (reminder,) = report["reminders"]
    assert report["summary"]["guard_reminders"] == 1
    assert reminder["event_seq"] == original["seq"]
    assert reminder["source_form"] == "notice"
    assert reminder["reaction"] == "CHANGED"
    assert reminder["recovered"] is None


@pytest.mark.parametrize("command", ["inspect", "analyze"])
def test_cli_counts_literal_official_v4_notice(trace_file, guard_rows, capsys, command):
    rows, _ = guard_rows
    assert main([command, str(trace_file(rows)), "--format", "json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["summary"]["guard_reminders"] == 1
    assert report["summary"]["reactions"]["CHANGED"] == 1


@pytest.mark.parametrize(
    "decoy",
    [
        "text",
        "plugin_field",
        "summary",
        "event_source",
        "nested_message",
        "tool_arguments",
    ],
)
def test_reminder_mentions_outside_producer_kind_are_not_guards(trace_file, guard_rows, decoy):
    rows, event = guard_rows
    source = event["data"]["source"] = {"kind": "user"}
    if decoy == "text":
        event["data"]["content"] = [{"type": "text", "text": "repeat-tool-reminder"}]
    elif decoy == "plugin_field":
        source["plugin"] = "repeat-tool-reminder"
    elif decoy == "summary":
        source.update(kind="runtime-context", form="notice", summary="repeat-tool-reminder")
    elif decoy == "event_source":
        event["source"] = {"kind": "repeat-tool-reminder", "form": "notice"}
    elif decoy == "nested_message":
        event["data"]["message"] = {"source": {"kind": "repeat-tool-reminder"}}
    else:
        call = next(row for row in rows if row["type"] == "tool/call")
        call["data"]["arguments"] = json.dumps(
            {
                "source": {"kind": "repeat-tool-reminder", "form": "notice"},
            }
        )
    session = normalize_session(load_sessions(trace_file(rows))[0])
    assert analyze_session(session)["summary"]["guard_reminders"] == 0
    assert all(event.guard_name is None for event in session.events)


def test_retired_plugin_wrapper_in_v4_is_refused_not_silently_missed(trace_file, guard_rows):
    rows, event = guard_rows
    event["data"]["source"] = {
        "kind": "plugin",
        "plugin": "repeat-tool-reminder",
        "form": "notice",
        "summary": "read × 3",
    }
    with pytest.raises(InputError, match="retired plugin source"):
        normalize_session(load_sessions(trace_file(rows))[0])


def test_cli_retired_wrapper_error_omits_message_payload(trace_file, guard_rows, capsys):
    rows, event = guard_rows
    event["data"]["source"] = {
        "kind": "plugin",
        "plugin": "repeat-tool-reminder",
        "form": "notice",
        "summary": "SYNTHETIC-PRIVATE-SUMMARY",
    }
    event["data"]["content"][0]["text"] = "SYNTHETIC-PRIVATE-BODY"
    assert main(["analyze", str(trace_file(rows)), "--format", "json"]) == 2
    captured = capsys.readouterr()
    assert not captured.out
    assert "retired plugin source" in captured.err
    assert "SYNTHETIC-PRIVATE" not in captured.err


def test_legacy_v3_header_is_not_implicitly_reinterpreted_as_v4(trace_file, guard_rows):
    rows, _ = deepcopy(guard_rows)
    rows[0]["version"] = 3
    with pytest.raises(InputError, match="only v4 is supported"):
        load_sessions(trace_file(rows))
