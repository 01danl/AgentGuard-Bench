"""Synthetic Harness v4 data only; never real user logs."""

import json
from pathlib import Path

import pytest


def make_trace(
    calls: list[tuple[str, str]],
    *,
    session_id: str = "synthetic-test",
    guard_after: int | None = None,
    interrupted: bool = False,
) -> list[dict]:
    rows = [
        {
            "type": "session",
            "version": 4,
            "id": session_id,
            "createdAt": 1,
            "isSeeded": False,
            "delegationDepth": 0,
        }
    ]

    def emit(kind: str, data: dict, **extra) -> None:
        rows.append({"type": kind, "seq": len(rows) - 1, "time": len(rows), "data": data, **extra})

    emit("turn/start", {"turn": 1})
    for step, (name, arguments) in enumerate(calls, start=1):
        emit("step/start", {"turn": 1, "step": step})
        if step == 1:
            emit(
                "system/message",
                {
                    "turn": 1,
                    "step": 1,
                    "message": {
                        "id": "system-1",
                        "role": "system",
                        "source": {"kind": "system-prompt"},
                        "content": [{"type": "text", "text": "Synthetic evaluation assistant."}],
                    },
                },
                surfaceOp="append",
            )
            emit(
                "user/message",
                {
                    "id": "user-1",
                    "role": "user",
                    "source": {"kind": "user"},
                    "content": [
                        {"type": "text", "text": "Синтетическая задача — inspect fixture."}
                    ],
                },
                surfaceOp="append",
            )
            emit(
                "request/header",
                {
                    "reason": "initial",
                    "header": {
                        "config": {"provider": "synthetic", "model": "synthetic"},
                    },
                },
            )
        if guard_after == step - 1:
            emit(
                "user/message",
                {
                    "id": f"reminder-{step}",
                    "role": "user",
                    "source": {
                        "kind": "repeat-tool-reminder",
                        "form": "notice",
                        "summary": f"{name} × {guard_after}",
                    },
                    "content": [{"type": "text", "text": "Synthetic repetition reminder."}],
                },
                surfaceOp="append",
            )
        call_id = f"call-{step}"
        emit(
            "assistant/message",
            {
                "turn": 1,
                "step": step,
                "message": {
                    "id": f"assistant-{step}",
                    "role": "assistant",
                    "source": {"kind": "model", "provider": "synthetic", "model": "synthetic"},
                    "content": [
                        {"type": "tool-call", "id": call_id, "name": name, "arguments": arguments}
                    ],
                },
                "stream": [],
            },
            surfaceOp="append",
        )
        emit(
            "tool/call",
            {"turn": 1, "step": step, "callId": call_id, "name": name, "arguments": arguments},
        )
        if interrupted and step == len(calls):
            break
        emit(
            "tool/result",
            {
                "turn": 1,
                "step": step,
                "message": {
                    "id": f"result-{step}",
                    "role": "tool",
                    "source": {"kind": "tool", "callId": call_id},
                    "toolCallId": call_id,
                    "content": [{"type": "text", "text": "Synthetic output"}],
                    "isError": False,
                },
            },
            surfaceOp="append",
        )
        emit("step/end", {"turn": 1, "step": step})
    if not interrupted:
        emit("turn/end", {"turn": 1, "reason": {"kind": "completed"}})
    return rows


def write_trace(path: Path, rows: list[dict]) -> Path:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )
    return path


@pytest.fixture
def trace_file(tmp_path):
    def write(rows):
        return write_trace(tmp_path / "synthetic.jsonl", rows)

    return write
