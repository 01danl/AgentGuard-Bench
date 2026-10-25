"""Render only the safe report projection. Never serialize internal dataclasses."""

import json
from typing import Any


def json_report(report: dict[str, Any]) -> str:
    return json.dumps(report, ensure_ascii=True, allow_nan=False, indent=2) + "\n"


def _quoted(value: Any) -> str:
    # Escape untrusted filenames and identifiers, including terminal control characters.
    return json.dumps(value, ensure_ascii=True)


def text_report(report: dict[str, Any], *, details: bool = True) -> str:
    summary = report["summary"]
    lines = [
        "AgentGuard Bench 0.1 — offline observations",
        f"Sessions: {summary['sessions']} | Events: {summary['events']} "
        f"(inherited: {summary['inherited_events']})",
        f"Tool calls: {summary['tool_calls']} | Exact repeats: {summary['exact_repeats']} "
        f"| Guard reminders: {summary['guard_reminders']}",
        f"Missing tool results: {summary['missing_tool_results']}",
        "Reactions: " + ", ".join(f"{key}={value}" for key, value in summary["reactions"].items()),
    ]
    for session in report["sessions"]:
        lines.append(
            f"\nSession {_quoted(session['session_id'])} from {_quoted(session['source'])}"
        )
        if session["open_turns_at_end"]:
            lines.append(f"  Open turns at end of log: {session['open_turns_at_end']}")
        for warning in session["warnings"]:
            lines.append(f"  Warning: {warning}")
        for repetition in session["repetitions"]:
            lines.append(
                f"  Repeated call: seq {repetition['previous_seq']} -> {repetition['seq']} "
                f"({repetition['action_id']}, streak={repetition['streak_length']})"
            )
        for reminder in session["reminders"]:
            following = [call["seq"] for call in reminder["following_calls"]]
            lines.append(
                f"  Guard seq {reminder['event_seq']}: {reminder['reaction']} "
                f"| trigger={reminder['trigger_call_seq']} ({reminder['trigger_attribution']}) "
                f"| following seqs={following} "
                f"| window={reminder['window_observed']}/{report['window']}"
            )
        if details:
            for call in session["tool_calls"]:
                lines.append(
                    f"  Call seq {call['seq']}: {_quoted(call['tool_name'])} "
                    f"action={call['action_id']} result_seq={call['result_seq']} "
                    f"is_error={_quoted(call['is_error'])}"
                )
    lines.append(
        "\nCHANGED does not mean RECOVERED. Task success and guard causal effect: unknown."
    )
    lines.append("Arguments, tool results and message text are omitted.")
    return "\n".join(lines) + "\n"
