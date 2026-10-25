import json
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import make_trace

from agentguard.cli import main


@pytest.mark.parametrize("command", ["inspect", "analyze"])
@pytest.mark.parametrize("output_format", ["text", "json"])
def test_cli_omits_arguments_results_messages(trace_file, capsys, command, output_format):
    secret = "sk-SYNTHETIC-DO-NOT-LEAK"
    rows = make_trace([("bash", json.dumps({"command": secret}))] * 4, guard_after=3)
    for row in rows:
        if row["type"] == "user/message":
            row["data"]["content"] = [{"type": "text", "text": secret}]
            row["data"]["source"]["summary"] = secret
        if row["type"] == "tool/result":
            row["data"]["message"]["content"] = [{"type": "text", "text": secret}]
    assert main([command, str(trace_file(rows)), "--format", output_format]) == 0
    captured = capsys.readouterr()
    assert secret not in captured.out + captured.err
    if output_format == "json":
        report = json.loads(captured.out)
        assert report["summary"]["reactions"]["IGNORED"] == 1
        assert report["sessions"][0]["reminders"][0]["event_seq"] >= 0
    else:
        assert "IGNORED=1" in captured.out
        assert "following seqs=" in captured.out


def test_cli_error_is_sanitized(tmp_path, capsys):
    path = tmp_path / "bad.jsonl"
    path.write_text('{"secret":"SYNTHETIC-SECRET",oops}')
    assert main(["analyze", str(path), "--format", "json"]) == 2
    captured = capsys.readouterr()
    assert not captured.out
    assert "SYNTHETIC-SECRET" not in captured.err
    assert "line 1" in captured.err


def test_cli_terminal_controls_escaped(trace_file, capsys):
    rows = make_trace([("bad\x1b[31mtool", "{}")], session_id="bad\x1b[31mid")
    assert main(["analyze", str(trace_file(rows))]) == 0
    assert "\x1b" not in capsys.readouterr().out


def test_module_entrypoint_fixture():
    path = Path(__file__).parent / "fixtures" / "synthetic-ignored.jsonl"
    result = subprocess.run(
        [sys.executable, "-m", "agentguard", "analyze", str(path), "--format", "json"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout)["summary"]["guard_reminders"] == 1


def test_invalid_window(trace_file):
    with pytest.raises(SystemExit) as error:
        main(["analyze", str(trace_file(make_trace([]))), "--window", "0"])
    assert error.value.code == 2
