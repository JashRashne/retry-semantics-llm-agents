"""Canonical JSON serialization frozen by ``primary-create-v1.1``."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any


def _validate_json_value(value: Any, active_containers: set[int]) -> None:
    """Reject values that are not exactly representable by the JSON data model."""

    if value is None or isinstance(value, (str, bool)):
        return
    if type(value) is int:  # bool is intentionally handled above.
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("non-finite floats are not valid JSON values")
        return

    if type(value) not in (list, dict):
        raise TypeError(f"unsupported non-JSON type: {type(value).__name__}")

    identity = id(value)
    if identity in active_containers:
        raise ValueError("circular JSON value")
    active_containers.add(identity)
    try:
        if type(value) is list:
            for item in value:
                _validate_json_value(item, active_containers)
        else:
            for key, item in value.items():
                if type(key) is not str:
                    raise TypeError("JSON object keys must be strings")
                _validate_json_value(item, active_containers)
    finally:
        active_containers.remove(identity)


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize a JSON value using the frozen canonical UTF-8 representation.

    Keys are recursively sorted, separators are compact, Unicode code points are
    encoded directly as UTF-8, and no BOM or trailing newline is added. Values
    outside the JSON data model are rejected instead of being coerced.
    """

    _validate_json_value(value, set())
    text = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return text.encode("utf-8")


def sha256_hex(data: bytes) -> str:
    """Return the lowercase SHA-256 digest of an exact byte sequence."""

    if type(data) is not bytes:
        raise TypeError("sha256_hex requires bytes")
    return hashlib.sha256(data).hexdigest()

