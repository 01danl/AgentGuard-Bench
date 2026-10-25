"""Command-line entry point; no network or Harness runtime is needed."""

import argparse
import sys
from collections.abc import Sequence

from . import __version__
from .analyzer import analyze_sessions
from .loader import load_sessions
from .models import InputError, Limits
from .normalize import normalize_session
from .report import json_report, text_report


def _positive(value: str) -> int:
    try:
        result = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("expected a positive integer") from None
    if result < 1:
        raise argparse.ArgumentTypeError("expected a positive integer")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline DeepSeek Harness v4 session analyzer")
    parser.add_argument("--version", action="version", version=f"agentguard {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("inspect", "analyze"):
        sub = commands.add_parser(command, help=f"{command.capitalize()} JSONL or ZIP sessions")
        sub.add_argument("path")
        sub.add_argument(
            "--window", type=_positive, default=5, help="Post-reminder tool-call window"
        )
        sub.add_argument("--format", choices=("text", "json"), default="text")
        sub.add_argument("--max-input-mib", type=_positive, default=64)
        sub.add_argument("--max-total-mib", type=_positive, default=128)
    args = parser.parse_args(argv)
    try:
        limits = Limits(
            max_input_bytes=args.max_input_mib * 1024 * 1024,
            max_total_bytes=args.max_total_mib * 1024 * 1024,
        )
        loaded = load_sessions(args.path, limits)
        sessions = tuple(normalize_session(session) for session in loaded)
        report = analyze_sessions(sessions, args.window)
        output = (
            json_report(report)
            if args.format == "json"
            else text_report(report, details=args.command == "analyze")
        )
        sys.stdout.write(output)
        return 0
    except InputError as error:
        # JSON diagnostics also escape hostile paths without leaking source lines.
        from json import dumps

        sys.stderr.write(f"agentguard: {dumps(str(error), ensure_ascii=True)}\n")
        return 2
    except BrokenPipeError:
        return 0
