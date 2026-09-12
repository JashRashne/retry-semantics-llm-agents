from __future__ import annotations

import math

import pytest

from retry_semantics.serialization import canonical_json_bytes, sha256_hex


def test_dictionary_insertion_order_does_not_affect_canonical_bytes() -> None:
    first = {"z": 3, "nested": {"b": 2, "a": 1}}
    second = {"nested": {"a": 1, "b": 2}, "z": 3}

    assert canonical_json_bytes(first) == canonical_json_bytes(second)


def test_semantically_equal_json_values_serialize_identically() -> None:
    first = {"items": [{"right": True, "left": None}], "name": "snowman ☃"}
    second = {"name": "snowman ☃", "items": [{"left": None, "right": True}]}

    assert canonical_json_bytes(first) == canonical_json_bytes(second)


def test_changed_value_changes_hash() -> None:
    before = canonical_json_bytes({"count": 1})
    after = canonical_json_bytes({"count": 2})

    assert sha256_hex(before) != sha256_hex(after)


def test_exact_compact_utf8_representation_has_no_newline_or_bom() -> None:
    result = canonical_json_bytes({"z": "☃", "a": [1, "line\nfeed"]})

    assert result == b'{"a":[1,"line\\nfeed"],"z":"\xe2\x98\x83"}'
    assert type(result) is bytes
    assert result.decode("utf-8") == '{"a":[1,"line\\nfeed"],"z":"☃"}'
    assert not result.startswith(b"\xef\xbb\xbf")
    assert not result.endswith(b"\n")


@pytest.mark.parametrize(
    "value",
    [
        {1: "non-string key"},
        ("tuple",),
        {"set": {1}},
        {"bytes": b"not JSON"},
        {"nan": math.nan},
        {"infinity": math.inf},
    ],
)
def test_non_json_values_are_rejected(value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        canonical_json_bytes(value)


def test_circular_json_value_is_rejected() -> None:
    value: list[object] = []
    value.append(value)

    with pytest.raises(ValueError, match="circular"):
        canonical_json_bytes(value)


def test_sha256_requires_actual_bytes() -> None:
    with pytest.raises(TypeError):
        sha256_hex("not bytes")  # type: ignore[arg-type]

