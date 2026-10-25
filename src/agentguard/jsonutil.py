"""Strict, deterministic JSON parsing without silently discarding duplicate keys."""

import json
import math
from dataclasses import dataclass
from typing import Any


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise ValueError("Non-finite JSON number")


def parse_json(text: str) -> Any:
    return json.loads(
        text, object_pairs_hook=_object, parse_constant=_constant, parse_float=_finite_float
    )


def _finite_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise ValueError("JSON number exceeds supported finite range")
    return value


def canonical_arguments(arguments: str) -> tuple[str, str]:
    """Keep malformed/ambiguous arguments byte-for-byte as decoded Unicode.

    The tagged raw fallback cannot collide with a valid JSON string value.
    JSON number spelling is preserved by custom parse hooks: 1 and 1.0 are
    conservatively distinct, as are -0 and 0. No JavaScript float rounding.
    """
    try:
        # Every node is tagged, so number tokens cannot collide with JSON arrays or strings.
        value = json.loads(
            arguments,
            object_pairs_hook=_object,
            parse_constant=_constant,
            parse_int=_Number,
            parse_float=_Number,
        )
        return "json", json.dumps(_tag(value), ensure_ascii=True, separators=(",", ":"))
    except (ValueError, RecursionError):
        return "raw", arguments


@dataclass(frozen=True)
class _Number:
    text: str


def _tag(value: Any) -> Any:
    if isinstance(value, _Number):
        return ["number", value.text]
    if isinstance(value, dict):
        return ["object", [[key, _tag(value[key])] for key in sorted(value)]]
    if isinstance(value, list):
        return ["array", [_tag(item) for item in value]]
    return ["value", value]
